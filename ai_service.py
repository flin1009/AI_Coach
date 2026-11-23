import datetime
import re
import time
import warnings
from google import genai

# 抑制 Google GenAI SDK 針對單次對話 generate_content 的 AFC 警示訊息
warnings.filterwarnings("ignore", message=".*automatic function calling.*")

from config import (
    GEMINI_API_KEY,
    RUNNER_NAME,
    RUNNER_BIRTH_YEAR,
    RUNNER_PB,
    ZONE2_MAX_HR
)
from utils import get_local_now

def get_taiwan_weekday_info():
    """取得設定時區 (預設 UTC+8) 當前的星期資訊與是否為週末"""
    tw_now = get_local_now()
    weekday_idx = tw_now.weekday()  # 0: 週一, ..., 5: 週六, 6: 週日
    weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    weekday_str = weekday_names[weekday_idx]
    is_weekend = weekday_idx in (5, 6)
    return tw_now, weekday_str, is_weekend

def get_genai_client():
    """初始化並回傳 Google GenAI 客戶端"""
    if not GEMINI_API_KEY:
        print("❌ 錯誤: 找不到 GEMINI_API_KEY 環境變數")
        return None
    return genai.Client(api_key=GEMINI_API_KEY)

def detect_candidate_models(client):
    """
    自動偵測可用高效率主力模型 (Flash / Hydrogen)，採用「跨世代多梯隊備援 (Cross-Generation Tiered Fallback)」：
    - 梯隊 1 (各前瞻大世代最新 1 款)：依大版本由高到低，每個大世代 (>= 3.x) 取最新 1 款 (例如 4.x Hydrogen、3.x Flash)
    - 梯隊 2 (旗艦生產主力)：gemini-2.5-flash (經千錘百鍊的成熟主力)
    - 梯隊 3 (成熟備援)：gemini-2.0-flash (不同 TPU 機房集群，隔離 503 尖峰)
    - 梯隊 4 (經典高可用)：gemini-1.5-flash
    - 梯隊 5 (輕量防穿透防線)：gemini-2.0-flash-lite (低延遲高通量，尖峰時負載極低)
    - 梯隊 6 (通用預設)：gemini-flash-latest
    徹底根除全選同一前瞻系列導致集體 503 UNAVAILABLE 斷線的風險！
    """
    fallback_chain = [
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-1.5-flash",
        "models/gemini-2.0-flash-lite",
        "models/gemini-flash-latest",
    ]
    if not client:
        return fallback_chain
    
    print("\n🔍 正在掃描可用 Gemini 模型陣列...")
    try:
        discovered = []
        available_names = set()
        for m in client.models.list():
            m_name = m.name.lower()
            # 檢查支援功能 (若有 supported_actions，需支援 generateContent)
            actions = getattr(m, 'supported_actions', None)
            if actions and 'generatecontent' not in [str(a).lower() for a in actions]:
                continue

            available_names.add(m_name.replace("models/", ""))

            if (
                ('flash' in m_name or 'hydrogen' in m_name)
                and 'lite' not in m_name
                and 'image' not in m_name
                and 'tts' not in m_name
                and 'live' not in m_name
            ):
                version_match = re.search(r'(\d+\.?\d*)', m_name)
                version = float(version_match.group(1)) if version_match else 0.0
                discovered.append((version, m.name))

        candidates = []
        seen = set()

        def add_candidate(raw_name):
            key = raw_name.lower().replace("models/", "")
            if key not in seen:
                seen.add(key)
                full_name = raw_name if raw_name.startswith("models/") else f"models/{raw_name}"
                candidates.append(full_name)

        if discovered:
            # 依版本高到低排序（同版本優先選名稱較短的正式代號）
            discovered.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)

            # 1. 各大世代 (>= 3.x) 各取最新 1 款 (例如 4.x Hydrogen、3.x Flash)
            seen_majors = set()
            for v, name in discovered:
                major = int(v)
                if major >= 3 and major not in seen_majors:
                    seen_majors.add(major)
                    add_candidate(name)

        # 2. 注入成熟生產主力與防穿透備援鏈 (若已取得可用模型清單，則過濾掉已下線模型避免 404 浪費重試)
        for stable in fallback_chain:
            stable_key = stable.lower().replace("models/", "")
            if not available_names or stable_key in available_names:
                add_candidate(stable)

        if candidates:
            print(f"✅ 自動構建跨世代階梯式備援陣列 ({len(candidates)} 款):")
            for idx, c in enumerate(candidates, 1):
                print(f"   [{idx}] {c}")
            return candidates
        else:
            print(f"⚠️ 未掃描到相符模型，採用預設階梯陣列: {' -> '.join(fallback_chain)}")
            return fallback_chain
    except Exception as e:
        print(f"❌ 掃描失敗: {e}，使用預設高可用階梯陣列")
        return fallback_chain

def _is_overload_error(err_str):
    """判斷是否為暫時性伺服器過載/超時錯誤 (可短暫退避重試 1 次再降級)"""
    lower = err_str.lower()
    return (
        "503" in err_str
        or "unavailable" in lower
        or "high demand" in lower
        or "500" in err_str
        or "internal" in lower
        or "deadline_exceeded" in lower
        or "timed out" in lower
    )


def _is_non_retryable_model_error(err_str):
    """判斷是否為不應對同一模型重試的錯誤 (例如 404 已下線、429 配額用盡、400/403)，應立即切換下一個備援模型"""
    lower = err_str.lower()
    return (
        "404" in err_str
        or "not_found" in lower
        or "not found" in lower
        or "429" in err_str
        or "resource_exhausted" in lower
        or "quota" in lower
        or "400" in err_str
        or "invalid_argument" in lower
        or "403" in err_str
        or "permission_denied" in lower
        or "deprecated" in lower
        or "not supported" in lower
    )


def _invoke_models_with_fallback(client, candidate_models, prompt, mode_label, fallback_503_advice, fallback_generic_suffix):
    """共用 Gemini 跨世代備援調用核心：支援錯誤分流、503 重試一次、404/429 立即切換與防禦性降級"""
    if not client:
        return (
            f"⚠️ 【AI 雲端分析暫時無法取得】：未初始化 AI 客戶端 (請檢查 GEMINI_API_KEY)\n{fallback_generic_suffix}",
            "fallback-rule-engine",
        )

    last_error = None
    tag = f" ({mode_label})" if mode_label else ""

    for model_name in candidate_models:
        for attempt in range(2):
            try:
                print(f"🤖 嘗試調用模型{tag}: {model_name} (第 {attempt + 1} 次)...")
                response = client.models.generate_content(model=model_name, contents=prompt)
                if response and response.text:
                    print(f"✨ 成功使用模型 {model_name} 完成{mode_label or '分析'}！")
                    return response.text, model_name
                raise ValueError("模型回應內容為空")
            except Exception as e:
                last_error = e
                err_str = str(e)
                print(f"⚠️ 模型 {model_name}{tag} 第 {attempt + 1} 次失敗: {err_str}")

                if _is_non_retryable_model_error(err_str):
                    print(f"   偵測到模型不可用或配額限制，立即切換至下一個備援模型...")
                    break
                if _is_overload_error(err_str):
                    if attempt == 0:
                        print("   伺服器暫時繁忙，等待 2 秒後重試一次...")
                        time.sleep(2)
                    else:
                        print(f"   模型 {model_name} 持續繁忙，立即自動容錯降級至下一個備援模型...")
                        break
                else:
                    if attempt == 0:
                        time.sleep(1)

    print(f"❌ 所有候選模型皆嘗試完畢，啟動防禦性降級指引: {last_error}")
    err_str = str(last_error) if last_error else "Unknown error"
    if _is_overload_error(err_str):
        return fallback_503_advice, "fallback-rule-engine"

    return (
        f"⚠️ 【AI 雲端分析暫時無法取得】：{err_str}\n{fallback_generic_suffix}",
        "fallback-rule-engine",
    )


_PLAIN_TEXT_FORMAT_RULE = (
    "格式要求：請使用純文字繁體中文，嚴禁使用 LaTeX 數學語法（例如請勿輸出 $\\rightarrow$ 或 \\rightarrow，"
    "若需箭頭請一律直接使用一般文字符號 → 或 ->）與 Markdown 語法符號（如 **粗體**、### 標題或 * 項目符號；條列請直接使用 • 或數字編號）。"
)


def generate_coach_advice(client, candidate_models, report_text):
    """依序調用候選模型進行教練分析 (支援 503 過載自動降級備援)"""
    tw_now, weekday_str, is_weekend = get_taiwan_weekday_info()
    today_date_str = tw_now.date().isoformat()
    yesterday_dt = tw_now.date() - datetime.timedelta(days=1)
    weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    yesterday_str = f"{yesterday_dt.isoformat()} ({weekday_names[yesterday_dt.weekday()]})"
    today_str = f"{today_date_str} ({weekday_str})"

    post_race_rule = (
        "       - 若昨日剛完成「正式賽事」，或報表中有「近期剛完賽目標賽事 (近7日內)」（特別是半馬/全馬或高負荷賽事），"
        "今日請優先依「賽後恢復期」原則調整（賽後 D+1 建議完全休跑或低衝擊散步；D+2~D+7 依生理恢復狀態與 ACWR 漸進恢復，"
        "僅安排極輕鬆 E 配速短距離恢復跑或持續休跑，切勿過早開立 M/T/I 強度課表）。"
    )

    if is_weekend:
        menu_instruction = f"""6. 【目標賽事備賽週期與今日訓練菜單 (今日 {today_str} 為假日，彈性時段指引)】：
       - 跑者假日作息說明：跑者假日作息彈性，出門跑步時段為「多數下午、其次晚間、少數早上」。
       - 請檢視「未來目標賽事」及其倒數天數/週數（例如：倒數 8 週代表處於基礎耐力期、倒數 4 週進入專項強度期、倒數 2 週進入賽前減量 Taper 期）。
{post_race_rule}
       - 綜合當前賽事備賽週期、ACWR 負荷比、最新生理恢復狀況與「今日訓練時段氣象預報 (若有)」，開立具體明確的「今日基準核心課表」（例如週末長距離慢跑 LSD、漸進耐力跑或主動恢復跑）。請指定訓練目的（E/M/T/I/R）、預計公里數、丹尼爾靶心配速與心率上限。
       - 時段動態微調指南：在課表下方，必須提供 3 種起跑時段的具體微調建議（依跑者今日實際出門時間與今日各時段預報的溫度、降雨機率、風速動態適配）：
         1. 🏃 【若選擇下午起跑 (首選推薦)】：人體核心體溫與肺活量處於全天巔峰，肌腱柔韌度高且午餐已轉化為充足肝醣，跑完不影響夜間睡眠。請全額執行原定課表（若體感良好後半程可微幅加溫至 M 配速）。叮嚀：午餐請於 12:00 前清淡用畢，出發前 1 小時補水 300ml。
         2. 🌅 【若改在早晨起跑 (次選/賽事模擬)】：若前晚有夜跑則間隔較短，且清晨肌肉較緊，建議課表縮減 2~3km 或降低強度（嚴格維持 Zone 2 以下），並加長 10 分鐘動態熱身；若接近賽季，可作為早餐時程與起跑生理時鐘模擬。
         3. 🌙 【若推遲至晚間起跑 (備選)】：為避免太晚跑完干擾夜間深度睡眠與自律神經 HRV，建議將距離收斂在 8~10km 以內，配速維持輕鬆體感，跑後加強下肢伸展與溫水澡冷卻。
       - 菜單區塊標題請明確使用：🎯 【今日具體訓練菜單 ({today_str} 假日彈性時段指引)】"""
    else:
        menu_instruction = f"""6. 【目標賽事備賽週期與今日訓練菜單 (今日 {today_str} 為平日，彈性時段指引)】：
       - 跑者作息說明：本報表於今日 ({today_str}) 清晨送達。為適應不同跑者之生活型態（晨跑族 vs. 夜跑族），請開立一套「今日基準核心課表」，並提供晨間與夜間二擇一的執行指引。
       - 請檢視「未來目標賽事」及其倒數天數/週數（例如：倒數 8 週代表處於基礎耐力期、倒數 4 週進入專項強度期、倒數 2 週進入賽前減量 Taper 期）。
{post_race_rule}
       - 綜合當前賽事備賽週期、ACWR 負荷比、最新生理恢復狀況與「今日訓練時段氣象預報 (若有)」，開立具體明確的今日「基準核心課表」（指定訓練目的 E/M/T/I/R、預計公里數、丹尼爾靶心配速範圍與心率上限）。
       - 請在菜單中特別註明：(💡 本日課表僅需擇一執行，請依您的平日作息選擇時段，切勿一日雙練)
       - 時段動態微調指南（必須同時呈現晨間與夜間建議，並結合今日清晨/晚間預報之降雨機率、氣溫與風速提醒裝備與補水或跑步機備案）：
         1. 🌅 【若您選擇晨間起跑 (晨跑族)】：剛起床核心體溫偏低、關節肌腱較緊且處於空腹狀態。請務必加長 8~10 分鐘動態暖身（著重踝關節與髖部），前 1~2 公里刻意放慢配速喚醒神經；心率以 Zone 2 為主（或質量課表前充分慢跑開關）；跑後補充電解質與優質蛋白質早餐開啟工作日。
         2. 🌙 【若您選擇晚間起跑 (夜跑族)】：肌肉神經反應好、整日肝醣充足，但累積整日工作與久坐疲勞。提醒下午 16:30 補充少量碳水點心（如香蕉/能量棒）與水分；下班以心率/自覺量表 (RPE) 抗衡工作疲勞（切勿盲目硬追死板配速）；跑後務必充分伸展收操，並洗溫水澡冷卻神經，避免交感神經亢奮影響夜間深度睡眠與自律神經 HRV。
       - 菜單區塊標題請明確使用：🎯 【今日具體訓練菜單 ({today_str} 平日彈性執行)】"""

    prompt = f"""
    你是一位專業的馬拉松教練。請分析 {RUNNER_NAME} 的運動數據。
    時間基準：報告發送日（今日）為 {today_str} 清晨；本次深度復盤對象為昨日 {yesterday_str} 的訓練紀錄。
    背景：{RUNNER_BIRTH_YEAR} 年生、全馬 PB {RUNNER_PB}、Zone 2 心率上限 {ZONE2_MAX_HR}bpm。

    數據包含以下幾大維度：
    A. 【丹尼爾 VDOT 靶心配速指針】：包含跑者在當前全馬 PB 換算之 VDOT 水準下的五大科學訓練靶心配速 (E/M/T/I/R)。
    B. 【急性與慢性負荷比 (ACWR)】：評估截至昨日之近 7 日急劇疲勞與近 28 日慢性體能之比值，判定目前處於甜點區 (Sweet Spot)、疲勞累積還是高受傷風險。
    C. 【今日生理恢復狀態 (若有)】：包含夜間 HRV (7日均值/狀態)、靜止心率與身體電量，評估自律神經與中樞神經修復準備度。
    D. 【目標賽事脈絡 (若有)】：包含「近期剛完賽目標賽事 (近7日內)」與距離今日 ({today_date_str}) 90 天內的「未來目標賽事」（比賽日期、距離與倒數/完賽天數）。
    E. 【今日訓練時段氣象預報 (若有)】：提供今日 ({today_str}) 清晨、下午與晚間的氣溫、體感、濕度、降雨機率與風速。
    F. 【近期訓練歷程 (截至昨日摘要)】：提供近一週的累積跑量、交叉訓練頻率與急劇疲勞脈絡。
    G. 【昨日活動深度數據】：包含昨日 ({yesterday_str}) 主要活動的分圈、心率區間 (Z1~Z5)、前後半程有氧解耦率 (Decoupling %)、跑步動態、功率與當時環境氣象。

    請針對以下重點提供深入分析與專業建議：(若活動沒有某些指標就不需強行分析；請明確區分「昨日活動復盤」與「今日訓練計畫」)
    (Garmin手錶上的Zone劃分與一般Zone劃分不同，請在分析時注意到這一點。)
    1. 【昨日活動型態判斷與品質點評】：請勿預設昨日訓練一定是 Zone 2。請依據實際配速、心率、心率區間分佈 (Z1~Z5)、功率、步頻與賽事標記，客觀判斷昨日 ({yesterday_str}) 這趟活動進行的是何種訓練（例如：正式賽事 (Race Day)、輕鬆恢復跑、Zone 2 有氧跑、馬拉松配速跑 MP、乳酸閾值/節奏跑 Tempo、間歇訓練 Interval、長距離慢跑 LSD 等）。若昨日活動數據或近期歷程已標註「🏁 賽事關聯 / 🏁 賽事標記 / 正式賽事」，務必直接將訓練型態判定為「正式賽事（並帶入賽事名稱與距離）」，改以實戰完賽策略、前後半程配速分配、心率控管與 VDOT 目標落差進行賽後復盤，切勿誤判為模擬跑或一般長距離訓練；否則請對照跑者的「丹尼爾 VDOT 靶心配速 (E/M/T/I/R)」點評執行強度是否達標。
    2. 【跑步效率與有氧解耦診斷】：結合「前後半程有氧解耦率 (Decoupling %)」、「跑步功率 (W)」與「昨日環境氣象（溫濕度、體感、風速）」，精準診斷心率漂移情況（<5% 代表耐力底層極佳；>8% 代表顯著漂移），分析是導因於補水散熱問題（熱蓄積）還是該配速超出身體有氧能力。（註：若報告已標註「非穩態/間歇課表僅供參考」，請勿將間歇配速落差誤判為有氧能力不足。）
    3. 【進階跑步動態診斷】：分析「步頻、步幅、垂直振幅、步幅比、觸地時間」，診斷跑姿經濟性、觸地負擔與潛在受傷風險。
    4. 【昨日環境與生理耗損】：結合昨日活動當下「環境氣象」與地形起伏，評估外部環境對心率飄移、出汗量與耐力消耗的加成影響。
    5. 【連續性與節奏】：檢查總時間與移動時間差距，評估昨日訓練停頓與連續性。
    {menu_instruction}
    
    語氣請保持專業、精確，並帶一點工程師的簡潔感。
    {_PLAIN_TEXT_FORMAT_RULE}
    數據內容：
    {report_text}
    """

    fallback_503 = (
        "⚠️ 【AI 雲端服務目前處於全球尖峰負載 (503 UNAVAILABLE)】\n"
        "Google Gemini 伺服器流量激增，系統已自動依序嘗試跨世代備援模型仍暫時無法取得生成。\n\n"
        "💡 【跑者今日自主調節指引】：\n"
        "• 請依據報表上方【丹尼爾 VDOT 靶心配速指針】自主鎖定今日課表配速。\n"
        "• 檢視【ACWR 體能負荷比】：若在 0.8~1.3 甜點區可照常執行基準課表；若 > 1.3 請主動縮減 20% 跑量或降為輕鬆跑 (E 配速)。\n"
        "• 賽事倒數提醒：專項準備期請著重特定靶心配速穩定度，注意水分補給與跑後充分放鬆！"
    )
    fallback_generic_suffix = "💡 建議依據報表上方【丹尼爾 VDOT 靶心配速】與【ACWR 體能負荷比】自主調配今日課表。"

    return _invoke_models_with_fallback(
        client,
        candidate_models,
        prompt,
        mode_label="",
        fallback_503_advice=fallback_503,
        fallback_generic_suffix=fallback_generic_suffix,
    )


def generate_rest_day_advice(client, candidate_models, report_text):
    """依序調用候選模型進行休息日/超補償教練分析 (支援 503 過載自動降級備援)"""
    tw_now, weekday_str, is_weekend = get_taiwan_weekday_info()
    today_date_str = tw_now.date().isoformat()
    yesterday_dt = tw_now.date() - datetime.timedelta(days=1)
    weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    yesterday_str = f"{yesterday_dt.isoformat()} ({weekday_names[yesterday_dt.weekday()]})"
    today_str = f"{today_date_str} ({weekday_str})"

    post_race_rest_rule = (
        "       - 若報表顯示「昨日目標賽事日」或「近期剛完賽目標賽事 (近7日內)」（例如剛完成半馬/全馬），"
        "即使 ACWR 下降或單日 HRV 回升，仍須優先遵守賽後漸進恢復期（全馬後一週以完全休息、步行或極短程輕鬆慢跑為主，嚴禁急於重啟高強度課表）。"
    )

    if is_weekend:
        rest_instruction = f"""4. 【目標賽事備賽週期與今日 ({today_str} 假日) 訓練／休整規劃】：
       - 跑者作息說明：跑者昨日 ({yesterday_str}) 未安排運動紀錄（已完成一日休整）；今日 ({today_str}) 為假日（作息彈性：多數下午、其次晚間、少數早上）。
       - 檢視「近期剛完賽目標賽事」、「未來目標賽事」及其倒數天數/週數與今日氣象預報，判斷當前週期階段。若 ACWR 與恢復狀態已就緒，請開立具體明確的「今日重啟訓練課表」（指定 E/M/T/I/R 訓練目的、精確公里數、丹尼爾靶心配速與時段建議）；若仍處於高疲勞警戒區或賽後恢復週，則明確建議今日持續休整或僅輕度恢復，並預告明日課表。
{post_race_rest_rule}
       標題請使用：🎯 【今日訓練重啟／休整指引 ({today_str} 假日)】"""
    else:
        rest_instruction = f"""4. 【目標賽事備賽週期與今日 ({today_str} 平日) 訓練／休整規劃】：
       - 跑者作息說明：本報表於今日 ({today_str}) 清晨送達。跑者昨日 ({yesterday_str}) 無運動紀錄（已完成一日休整）。
       - 檢視「近期剛完賽目標賽事」、「未來目標賽事」及其倒數天數/週數與今日氣象預報，判斷當前週期階段。若 ACWR 與恢復狀態已就緒，請開立具體明確的「今日重啟訓練課表」（指定 E/M/T/I/R 訓練目的、精確公里數、丹尼爾靶心配速，並提供晨間／晚間二擇一指引）；若仍處於高疲勞警戒區或賽後恢復週，則建議今日持續休整或僅輕度恢復並預告明日課表。
{post_race_rest_rule}
       標題請使用：🎯 【今日訓練重啟／休整指引 ({today_str} 平日)】"""

    prompt = f"""
    你是一位專業的馬拉松耐力運動教練。
    時間基準：報告發送日（今日）為 {today_str} 清晨；跑者昨日 ({yesterday_str}) 為「休息日 / 無運動紀錄」。
    背景：{RUNNER_NAME}，{RUNNER_BIRTH_YEAR} 年生、全馬 PB {RUNNER_PB}、Zone 2 心率上限 {ZONE2_MAX_HR}bpm。
    
    在耐力訓練中，適當的休息與超補償 (Supercompensation) 是體能躍升與預防過度訓練的關鍵。
    請根據跑者截至昨日的訓練歷程、近期剛完賽賽事 (若有)、ACWR 負荷、今日生理恢復數據與今日氣象預報，評估昨日休整後的超補償成果，並提供專業、科學且具體可行的「今日 ({today_str}) 體能評估與訓練建議」。

    請針對以下 4 點重點提供分析與建議：
    1. 【週期負荷與超補償診斷】：結合 ACWR (急劇與慢性負荷比)、今日生理恢復狀態 (若有 HRV/靜止心率/電量) 與近7日內完賽賽事/長距離高負荷紀錄，評估經過昨日休整後，身體目前處於賽後修復期、減量恢復期、最佳適應甜點期還是仍處疲勞警戒期。
    2. 【主動恢復與筋膜保養處方】：給予今日具體的身體保養指引（例如：泡沫軸滾筒放鬆、髖關節/小腿動態伸展或輕度步行）。
    3. 【營養、補水與修復關鍵】：針對耐力跑者的肌肉修復，提醒飲食重點（優質蛋白質攝取、水分電解質平衡與睡眠修復建議）。
    {rest_instruction}

    語氣請保持專業、鼓勵、精準，並帶一點工程師的科學簡潔感。
    {_PLAIN_TEXT_FORMAT_RULE}
    歷史與統計數據：
    {report_text}
    """

    fallback_503 = (
        "⚠️ 【AI 雲端服務目前處於全球尖峰負載 (503 UNAVAILABLE)】\n"
        "Google Gemini 伺服器流量激增，系統已自動依序嘗試跨世代備援模型仍暫時無法取得生成。\n\n"
        "🌿 【今日休整自主指引】：\n"
        "• 今日為排定之體能休整日，重點在於讓自律神經與下肢肌群獲得超補償 (Supercompensation)。\n"
        "• 建議進行 15~20 分鐘下肢筋膜滾筒放鬆或溫和伸展，補足水分與優質蛋白質。\n"
        "• 靜待心肺與神經疲勞完全消退，儲備下次課表的飽滿體能！"
    )
    fallback_generic_suffix = "🌿 今日為排定之休整日，建議進行主動伸展與充足休息。"

    return _invoke_models_with_fallback(
        client,
        candidate_models,
        prompt,
        mode_label="休整模式",
        fallback_503_advice=fallback_503,
        fallback_generic_suffix=fallback_generic_suffix,
    )
