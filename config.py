import os

# --- 1. 帳號與密鑰設定 (由環境變數讀取) ---
# GitHub Actions 會將 Secrets 映射到這些變數名稱
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PWD = os.getenv("GARMIN_PWD")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- 2. 跑者背景參數 (優先讀取環境變數，兼顧個人隱私與預設泛用值) ---
RUNNER_NAME = os.getenv("RUNNER_NAME", "Runner")
RUNNER_BIRTH_YEAR = int(os.getenv("RUNNER_BIRTH_YEAR", "1985"))
RUNNER_PB = os.getenv("RUNNER_PB", "3:45")
ZONE2_MAX_HR = int(os.getenv("ZONE2_MAX_HR", "140"))

# --- 3. 系統與查詢參數 ---
ACTIVITIES_COUNT = int(os.getenv("ACTIVITIES_COUNT", "7"))
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "25.03"))   # 預設生活圈緯度 (室內無 GPS 活動之室外氣象備援)
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "121.56"))  # 預設生活圈經度 (室內無 GPS 活動之室外氣象備援)

# --- 4. 目錄設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_SAVE_DIR = os.path.join(CURRENT_DIR, "garmin_logs")
