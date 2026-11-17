import os


def _get_env(key, default=""):
    """安全讀取環境變數：若未設定或為空字串 (例如 GitHub Actions 未填寫的 Secrets)，回傳預設值"""
    val = os.getenv(key)
    if val is None:
        return default
    stripped = val.strip()
    return stripped if stripped else default


# --- 1. 帳號與密鑰設定 (由環境變數讀取) ---
# GitHub Actions 會將 Secrets 映射到這些變數名稱
GARMIN_EMAIL = _get_env("GARMIN_EMAIL", None)
GARMIN_PWD = _get_env("GARMIN_PWD", None)
TG_TOKEN = _get_env("TG_TOKEN", None)
TG_CHAT_ID = _get_env("TG_CHAT_ID", None)
GEMINI_API_KEY = _get_env("GEMINI_API_KEY", None)

# --- 2. 跑者背景參數 (優先讀取環境變數，兼顧個人隱私與預設泛用值) ---
RUNNER_NAME = _get_env("RUNNER_NAME", "Runner")
RUNNER_BIRTH_YEAR = int(_get_env("RUNNER_BIRTH_YEAR", "1985"))
RUNNER_PB = _get_env("RUNNER_PB", "3:45")
ZONE2_MAX_HR = int(_get_env("ZONE2_MAX_HR", "140"))

# --- 3. 系統與查詢參數 ---
TZ_OFFSET_HOURS = int(_get_env("TZ_OFFSET_HOURS", "8"))  # 預設台灣時區 (UTC+8)
ACTIVITIES_COUNT = int(_get_env("ACTIVITIES_COUNT", "7"))
DEFAULT_LAT = float(_get_env("DEFAULT_LAT", "25.03"))   # 預設生活圈緯度 (室內無 GPS 活動之室外氣象備援)
DEFAULT_LON = float(_get_env("DEFAULT_LON", "121.56"))  # 預設生活圈經度 (室內無 GPS 活動之室外氣象備援)

# --- 4. 目錄設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_SAVE_DIR = os.path.join(CURRENT_DIR, "garmin_logs")
