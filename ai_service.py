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

def get_taiwan_weekday_info():
    """取得台灣時間 (UTC+8) 當前的星期資訊與是否為週末"""
    try:
        from datetime import timezone
        tw_tz = timezone(datetime.timedelta(hours=8))
        tw_now = datetime.datetime.now(tw_tz)
    except Exception:
        tw_now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)

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
    """自動偵測可用 Flash 模型，並由新到舊排序保留前 3 名候選備援"""
    default_model = "models/gemini-flash-latest"
    if not client:
        return [default_model]
    
    print("\n🔍 正在掃描可用模型...")
    flash_models = []
    try:
        for m in client.models.list():
            m_name = m.name.lower()
            if 'flash' in m_name and 'image' not in m_name and 'tts' not in m_name and 'lite' not in m_name and 'live' not in m_name:
                version_match = re.search(r'(\d+\.?\d*)', m_name)
                version = float(version_match.group(1)) if version_match else 0.0
                flash_models.append((version, m.name))
        
        if flash_models:
            flash_models.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
            seen = set()
            candidates = []
            for _, name in flash_models:
                if name not in seen:
                    seen.add(name)
                    candidates.append(name)
                if len(candidates) >= 3:
                    break
            print(f"✅ 自動鎖定模型優先順序: {' -> '.join(candidates)}")
            return candidates
        else:
            print(f"⚠️ 使用備援模型: {default_model}")
            return [default_model]
    except Exception as e:
        print(f"❌ 偵測失敗: {e}")
        return [default_model]

def generate_coach_advice(client, candidate_models, report_text):
    """依序調用候選模型進行教練分析 (支援 503 過載自動降級備援)"""
    tw_now, weekday_str, is_weekend = get_taiwan_weekday_info()

    if is_weekend:
        menu_instruction = f"""6. 【目標賽事備賽週期與今日訓練菜單 (今日為{weekday_str}假日，彈性時段指引)】：
       - 跑者假日作息說明：跑者假日作息彈性，出門跑步時段為「多數下午、其次晚間、少數早上」。
       - 請檢視「未來目標賽事」及其倒數天數/週數（例如：倒數 8 週代表處於基礎耐力期、倒數 4 週進入專項強度期、倒數 2 週進入賽前減量 Taper 期）。
       - 綜合當前賽事備賽週期、ACWR 負荷比與最新生理恢復狀況，開立具體明確的「基準核心課表」（例如週末長距離慢跑 LSD、漸進耐力跑或主動恢復跑）。請指定訓練目的（E/M/T/I/R）、預計公里數、丹尼爾靶心配速與心率上限。
       - 時段動態微調指南：在課表下方，必須提供 3 種起跑時段的具體微調建議（依跑者今日實際出門時間動態適配）：
         1. 🏃 【若選擇下午起跑 (首選推薦)】：人體核心體溫與肺活量處於全天巔峰，肌腱柔韌度高且午餐已轉化為充足肝醣，跑完不影響夜間睡眠。請全額執行原定課表（若體感良好後半程可微幅加溫至 M 配速）。叮嚀：午餐請於 12:00 前清淡用畢，出發前 1 小時補水 300ml。
         2. 🌅 【若改在早晨起跑 (次選/賽事模擬)】：若前晚有夜跑則間隔較短，且清晨肌肉較緊，建議課表縮減 2~3km 或降低強度（嚴格維持 Zone 2 以下），並加長 10 分鐘動態熱身；若接近賽季，可作為早餐時程與起跑生理時鐘模擬。
         3. 🌙 【若推遲至晚間起跑 (備選)】：為避免太晚跑完干擾夜間深度睡眠與自律神經 HRV，建議將距離收斂在 8~10km 以內，配速維持輕鬆體感，跑後加強下肢伸展與溫水澡冷卻。
       - 菜單區塊標題請明確使用：🎯 【今日具體訓練菜單 (假日彈性時段指引)】"""
    else:
        menu_instruction = f"""6. 【目標賽事備賽週期與今日訓練菜單 (今日為{weekday_str}平日，彈性時段指引)】：
       - 跑者作息說明：本報表於每日清晨送達。為適應不同跑者之生活型態（晨跑族 vs. 夜跑族），請開立一套「基準核心課表」，並提供晨間與夜間二擇一的執行指引。
       - 請檢視「未來目標賽事」及其倒數天數/週數（例如：倒數 8 週代表處於基礎耐力期、倒數 4 週進入專項強度期、倒數 2 週進入賽前減量 Taper 期）。
       - 綜合當前賽事備賽週期、ACWR 負荷比與最新生理恢復狀況，開立具體明確的今日「基準核心課表」（指定訓練目的 E/M/T/I/R、預計公里數、丹尼爾靶心配速範圍與心率上限）。
       - 請在菜單中特別註明：(💡 本日課表僅需擇一執行，請依您的平日作息選擇時段，切勿一日雙練)
       - 時段動態微調指南（必須同時呈現晨間與夜間建議）：
         1. 🌅 【若您選擇晨間起跑 (晨跑族)】：剛起床核心體溫偏低、關節肌腱較緊且處於空腹狀態。請務必加長 8~10 分鐘動態暖身（著重踝關節與髖部），前 1~2 公里刻意放慢配速喚醒神經；心率以 Zone 2 為主（或質量課表前充分慢跑開關）；跑後補充電解質與優質蛋白質早餐開啟工作日。
         2. 🌙 【若您選擇晚間起跑 (夜跑族)】：肌肉神經反應好、整日肝醣充足，但累積整日工作與久坐疲勞。提醒下午 16:30 補充少量碳水點心（如香蕉/能量棒）與水分；下班以心率/自覺量表 (RPE) 抗衡工作疲勞（切勿盲目硬追死板配速）；跑後務必充分伸展收操，並洗溫水澡冷卻神經，避免交感神經亢奮影響夜間深度睡眠與自律神經 HRV。
       - 菜單區塊標題請明確使用：🎯 【今日具體訓練菜單 (平日彈性執行)】"""

    prompt = f"""
    你是一位專業的馬拉松教練。請分析 {RUNNER_NAME} 的運動數據。
    背景：{RUNNER_BIRTH_YEAR} 年生、全馬 PB {RUNNER_PB}、Zone 2 心率上限 {ZONE2_MAX_HR}bpm。

    數據包含以下幾大維度：
    A. 【丹尼爾 VDOT 靶心配速指針】：包含跑者在當前全馬 PB 換算之 VDOT 水準下的五大科學訓練靶心配速 (E/M/T/I/R)。
    B. 【急性與慢性負荷比 (ACWR)】：評估近 7 日急劇疲勞與近 28 日慢性體能之比值，判定目前處於甜點區 (Sweet Spot)、疲勞累積還是高受傷風險。
    C. 【今日生理恢復狀態 (若有)】：包含夜間 HRV (7日均值/狀態)、靜止心率與身體電量，評估自律神經與中樞神經修復準備度。
    D. 【未來目標賽事 (近三個月倒數) (若有)】：列出距離今日 90 天內的目標賽事、比賽日期、距離與倒數天數。
    E. 【近期訓練歷程 (近 7 筆摘要)】：提供近一週的累積跑量、交叉訓練頻率與急劇疲勞脈絡。
    F. 【最新活動深度數據】：包含最新一筆活動的分圈、心率區間 (Z1~Z5)、前後半程有氧解耦率 (Decoupling %)、跑步動態、功率與環境氣象。

    請針對以下重點提供深入分析與專業建議：(若活動沒有某些指標就不需強行分析)
    (Garmin手錶上的Zone劃分與一般Zone劃分不同，請在分析時注意到這一點。)
    1. 【最新活動型態判斷與品質點評】：請勿預設本次訓練一定是 Zone 2。請依據實際配速、心率、心率區間分佈 (Z1~Z5)、功率與步頻，客觀判斷最新這趟活動進行的是何種訓練（例如：輕鬆恢復跑、Zone 2 有氧跑、馬拉松配速跑 MP、乳酸閾值/節奏跑 Tempo、間歇訓練 Interval、長距離慢跑 LSD 等）。請務必對照跑者的「丹尼爾 VDOT 靶心配速 (E/M/T/I/R)」進行精準比對，點評執行強度是否達標。
    2. 【跑步效率與有氧解耦診斷】：結合「前後半程有氧解耦率 (Decoupling %)」、「跑步功率 (W)」與「環境氣象（溫濕度、體感）」，精準診斷心率漂移情況（<5% 代表耐力底層極佳；>8% 代表顯著漂移），分析是導因於補水散熱問題（熱蓄積）還是該配速超出身體有氧能力。
    3. 【進階跑步動態診斷】：分析「步頻、步幅、垂直振幅、步幅比、觸地時間」，診斷跑姿經濟性、觸地負擔與潛在受傷風險。
    4. 【環境與生理耗損】：結合活動當日「環境氣象」與地形起伏，評估外部環境對心率飄移、出汗量與耐力消耗的加成影響。
    5. 【連續性與節奏】：檢查總時間與移動時間差距，評估訓練停頓與連續性。
    {menu_instruction}
    
    語氣請保持專業、精確，並帶一點工程師的簡潔感。
    格式要求：請使用純文字繁體中文，嚴禁使用 LaTeX 數學語法（例如請勿輸出 $\rightarrow$ 或 \rightarrow，若需箭頭請一律直接使用一般文字符號 → 或 ->）。
    數據內容：
    {report_text}
    """
    last_error = None
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                print(f"🤖 嘗試調用模型: {model_name} (第 {attempt + 1} 次)...")
                response = client.models.generate_content(model=model_name, contents=prompt)
                print(f"✨ 成功使用模型 {model_name} 完成分析！")
                return response.text, model_name
            except Exception as e:
                last_error = e
                print(f"⚠️ 模型 {model_name} 第 {attempt + 1} 次失敗: {e}")
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    print("   伺服器繁忙 (503)，等待 3 秒後重試或切換下一個模型...")
                    time.sleep(3)
                else:
                    time.sleep(1)

    error_msg = f"AI error after retry across candidate models ({', '.join(candidate_models)}): {last_error}"
    return error_msg, candidate_models[0]

def generate_rest_day_advice(client, candidate_models, report_text):
    """依序調用候選模型進行休息日/超補償教練分析 (支援 503 過載自動降級備援)"""
    tw_now, weekday_str, is_weekend = get_taiwan_weekday_info()

    if is_weekend:
        rest_instruction = f"""4. 【目標賽事備賽週期與今日休整/下次重啟訓練菜單 (今日為{weekday_str}假日)】：
       - 跑者作息說明：跑者假日作息彈性（多數下午、其次晚間、少數早上）。今日排定為休整日，請以跑者「週末主動恢復（泡沫軸滾筒放鬆、輕度散步、拉筋、身心放鬆超補償）」為核心。
       - 檢視是否有「未來目標賽事」及其倒數天數/週數，判斷當前備賽週期階段。結合跑者的體能恢復節奏與「丹尼爾 VDOT 靶心配速指針」，開立具體明確的下次/重啟訓練菜單（指定 E/M/T/I/R 訓練目的、精確公里數與靶心配速，例如安排輕量 E 配速跑 5~6km 喚醒神經肌肉，或具備重啟 Tempo / 間歇質量課表的條件）。標題請使用：🎯 【今日休整指引與重啟課表預告 (假日恢復)】"""
    else:
        rest_instruction = f"""4. 【目標賽事備賽週期與今日休整/下次重啟訓練菜單 (今日為{weekday_str}平日)】：
       - 跑者作息說明：今日排定為休整日，請以跑者「今日日間/晚間主動恢復」與「明日重啟課表」為視角。
       - 檢視是否有「未來目標賽事」及其倒數天數/週數，判斷當前備賽週期階段。結合跑者的體能恢復節奏與「丹尼爾 VDOT 靶心配速指針」，開立具體明確的明日重啟訓練菜單（指定 E/M/T/I/R 訓練目的、精確公里數與靶心配速，例如安排輕量 E 配速跑 5~6km 喚醒神經肌肉，或具備重啟 Tempo / 間歇質量課表的條件，並可依跑者偏好於明晨或明晚執行）。標題請使用：🎯 【今日休整指引與重啟課表預告 (平日恢復)】"""

    prompt = f"""
    你是一位專業的馬拉松耐力運動教練。{RUNNER_NAME} 今天處於「完全休息日 / 未排定跑步日」。
    背景：{RUNNER_BIRTH_YEAR} 年生、全馬 PB {RUNNER_PB}、Zone 2 心率上限 {ZONE2_MAX_HR}bpm。
    
    在耐力訓練中，適當的休息與超補償 (Supercompensation) 是體能躍升與預防過度訓練的關鍵。
    請根據跑者近期的訓練歷程、ACWR 負荷與生理恢復數據，提供一份專業、科學且具體可行的「今日休整與超補償指引」。

    請針對以下 4 點重點提供分析與建議：
    1. 【週期負荷與疲勞診斷】：結合 ACWR (急劇與慢性負荷比) 與生理恢復狀態 (若有 HRV/靜止心率/電量)，評估身體目前處於減量恢復期、最佳適應甜點期還是疲勞警戒期。
    2. 【今日主動恢復處方】：給予今日具體的休整指引（例如：是否適合進行 20~30 分鐘輕度散步、下肢筋膜滾筒放鬆、髖關節/小腿動態伸展，還是建議完全靜態休息）。
    3. 【營養、補水與修復關鍵】：針對耐力跑者的肌肉修復，提醒今日飲食重點（優質蛋白質攝取、水分電解質平衡與睡眠修復建議）。
    {rest_instruction}

    語氣請保持專業、鼓勵、精準，並帶一點工程師的科學簡潔感。
    格式要求：請使用純文字繁體中文，嚴禁使用 LaTeX 數學語法（例如請勿輸出 $\rightarrow$ 或 \rightarrow，若需箭頭請一律直接使用一般文字符號 → 或 ->）。
    歷史與統計數據：
    {report_text}
    """
    last_error = None
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                print(f"🤖 嘗試調用模型 (休整模式): {model_name} (第 {attempt + 1} 次)...")
                response = client.models.generate_content(model=model_name, contents=prompt)
                print(f"✨ 成功使用模型 {model_name} 完成休整分析！")
                return response.text, model_name
            except Exception as e:
                last_error = e
                print(f"⚠️ 模型 {model_name} 第 {attempt + 1} 次失敗: {e}")
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    print("   伺服器繁忙 (503)，等待 3 秒後重試或切換下一個模型...")
                    time.sleep(3)
                else:
                    time.sleep(1)

    error_msg = f"AI error after retry across candidate models ({', '.join(candidate_models)}): {last_error}"
    return error_msg, candidate_models[0]
