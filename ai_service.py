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
    prompt = f"""
    你是一位專業的馬拉松教練。請分析 {RUNNER_NAME} 的運動數據。
    背景：{RUNNER_BIRTH_YEAR} 年生、全馬 PB {RUNNER_PB}、Zone 2 心率上限 {ZONE2_MAX_HR}bpm。

    數據包含以下幾大維度：
    A. 【急性與慢性負荷比 (ACWR)】：評估近 7 日急劇疲勞與近 28 日慢性體能之比值，判定目前處於甜點區 (Sweet Spot)、疲勞累積還是高受傷風險。
    B. 【今日生理恢復狀態 (若有)】：包含夜間 HRV (7日均值/狀態)、靜止心率與身體電量，評估自律神經與中樞神經修復準備度。
    C. 【近期訓練歷程 (近 7 筆摘要)】：提供近一週的累積跑量、交叉訓練頻率與急劇疲勞脈絡。
    D. 【最新活動深度數據】：包含最新一筆活動的分圈、心率區間 (Z1~Z5)、跑步動態、功率與環境氣象。

    請針對以下重點提供深入分析與專業建議：(若活動沒有某些指標就不需強行分析)
    (Garmin手錶上的Zone劃分與一般Zone劃分不同，請在分析時注意到這一點。)
    1. 【最新活動型態判斷與品質點評】：請勿預設本次訓練一定是 Zone 2。請依據實際的配速、心率、心率區間分佈 (Z1~Z5)、功率與步頻數據，客觀判斷 {RUNNER_NAME} 最新這趟活動進行的是何種訓練（例如：輕鬆恢復跑、Zone 2 有氧基礎跑、馬拉松配速跑 MP、乳酸閾值/節奏跑 Tempo、間歇訓練 Interval、長距離慢跑 LSD 等），並針對該訓練目的深度點評執行品質。
    2. 【跑步效率與能量輸出】：結合「跑步功率 (W)」與「心率」，評估跑步效率 (Efficiency Factor = 功率 / 心率)，並觀察後半程是否有心率漂移（心率隨時間上升但配速/功率未變）現象。
    3. 【進階跑步動態診斷】：分析「步頻、步幅、垂直振幅、步幅比、觸地時間」，診斷跑姿經濟性、觸地負擔與潛在受傷風險。
    4. 【環境與生理耗損】：結合活動當日「環境氣象（氣溫、濕度、體感）」與地形起伏，評估熱壓力對心率漂移與補水散熱的影響。
    5. 【連續性與節奏】：檢查總時間與移動時間差距，評估訓練停頓與連續性。
    6. 【綜合 ACWR 負荷與週期課表建議】：結合 ACWR 負荷指數與今日生理恢復狀況（若有），評估目前處於體能適應甜點期還是過度疲勞期，具體為明天給出最合適的訓練或休整建議（例如：安排主動恢復跑、完全休息或安排質量課表）。
    
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
    prompt = f"""
    你是一位專業的馬拉松耐力運動教練。{RUNNER_NAME} 今天處於「完全休息日 / 未排定跑步日」。
    背景：{RUNNER_BIRTH_YEAR} 年生、全馬 PB {RUNNER_PB}、Zone 2 心率上限 {ZONE2_MAX_HR}bpm。
    
    在耐力訓練中，適當的休息與超補償 (Supercompensation) 是體能躍升與預防過度訓練的關鍵。
    請根據跑者近期的訓練歷程、ACWR 負荷與生理恢復數據，提供一份專業、科學且具體可行的「今日休整與超補償指引」。

    請針對以下 4 點重點提供分析與建議：
    1. 【週期負荷與疲勞診斷】：結合 ACWR (急劇與慢性負荷比) 與生理恢復狀態 (若有 HRV/靜止心率/電量)，評估身體目前處於減量恢復期、最佳適應甜點期還是疲勞警戒期。
    2. 【今日主動恢復處方】：給予今日具體的休整指引（例如：是否適合進行 20~30 分鐘輕度散步、下肢筋膜滾筒放鬆、髖關節/小腿動態伸展，還是建議完全靜態休息）。
    3. 【營養、補水與修復關鍵】：針對耐力跑者的肌肉修復，提醒今日飲食重點（優質蛋白質攝取、水分電解質平衡與睡眠修復建議）。
    4. 【下次重啟訓練課表預告】：依據跑者的體能恢復節奏，具體預告明天或下次重啟訓練時，建議執行何種課表（例如：輕量 Zone 2 恢復跑 5~6km 喚醒神經肌肉，或已具備安排 Tempo / 間歇質量課表的條件）。

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
