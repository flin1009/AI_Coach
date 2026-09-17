import base64
import datetime
import json
import os
from pathlib import Path
from garminconnect import Garmin
from config import GARMIN_EMAIL, GARMIN_PWD

# 支援本地與雲端 Token 快取目錄 (優先讀取 GARMINTOKENS 環境變數，預設為 ~/.garminconnect)
TOKEN_DIR = os.getenv("GARMINTOKENS", str(Path.home() / ".garminconnect"))

def restore_tokens_from_base64(b64_str, target_dir):
    """自 Base64 字串還原 Token 快取檔案"""
    raw_data = base64.b64decode(b64_str.strip().encode("utf-8")).decode("utf-8")
    tokens_dict = json.loads(raw_data)
    os.makedirs(target_dir, exist_ok=True)
    for filename, content in tokens_dict.items():
        filepath = os.path.join(target_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

def get_garmin_client():
    """登入並回傳 Garmin 客戶端實例（支援 Token 快取、Base64 Secret 注入與自動刷新）"""
    tokenstore_path = str(Path(TOKEN_DIR).expanduser())

    # 0. 若環境變數提供 GARMINTOKENS_BASE64 且本地快取目錄尚未還原，自動解碼還原
    token_b64 = os.getenv("GARMINTOKENS_BASE64")
    if token_b64 and not (os.path.exists(tokenstore_path) and os.listdir(tokenstore_path)):
        try:
            print("[Garmin] 偵測到 GARMINTOKENS_BASE64，正在還原 Token 快取至雲端環境...")
            restore_tokens_from_base64(token_b64, tokenstore_path)
            print("[Garmin] 成功自 GARMINTOKENS_BASE64 還原 Token 快取！")
        except Exception as b64_err:
            print(f"[Garmin] ⚠️ 自 GARMINTOKENS_BASE64 還原失敗 ({b64_err})，將嘗試正常登入...")

    # 1. 嘗試優先使用本地已保存之 Token 恢復連線 (避免重複走 SSO 帳密登入被限流)
    try:
        print(f"[Garmin] 嘗試使用 Token 快取恢復連線: {tokenstore_path}")
        client = Garmin()
        client.login(tokenstore_path)
        print("[Garmin] 登入成功 (已透過 Token 快取秒速恢復連線)")
        return client
    except Exception as token_err:
        print(f"[Garmin] 無法使用 Token 快取 ({token_err})，將回退使用帳號密碼進行登入...")

    # 2. 若無快取或快取無效，使用帳號密碼登入並自動儲存最新 Token
    if not GARMIN_EMAIL or not GARMIN_PWD:
        raise ValueError("找不到 GARMIN_EMAIL 或 GARMIN_PWD 環境變數，且無有效 Token 快取可用")

    try:
        os.makedirs(tokenstore_path, exist_ok=True)
        print("[Garmin] 正在透過帳號密碼連線 Garmin SSO 登入 (首次或快取過期)...")
        client = Garmin(GARMIN_EMAIL, GARMIN_PWD)
        client.login(tokenstore_path)
        print("[Garmin] 登入成功 (已儲存/更新 Token 快取)")
        return client
    except Exception as e:
        print(f"[Garmin] 帳密登入失敗: {e}")
        raise


def fetch_recent_activities(client, count=7):
    """取得近期運動活動"""
    try:
        return client.get_activities(0, count)
    except Exception as e:
        print(f"❌ 取得 Garmin 活動失敗: {e}")
        return []

def fetch_extended_activities(client, count=35):
    """取得過去約 4 週 (28~35天) 的長週期活動數據，供 ACWR 模型計算"""
    try:
        return client.get_activities(0, count)
    except Exception as e:
        print(f"⚠️ 取得長週期活動失敗 (將以近期活動估算): {e}")
        return []

def fetch_activity_splits(client, activity_id):
    """取得活動分圈數據"""
    try:
        splits = client.get_activity_splits(activity_id)
        return splits.get("lapDTOs", []) if splits else []
    except Exception:
        return []

def fetch_activity_hr_zones(client, activity_id):
    """取得活動心率區間分佈原始數據"""
    try:
        return client.get_activity_hr_in_timezones(activity_id)
    except Exception:
        return None

def fetch_daily_recovery_metrics(client, target_date=None):
    """嘗試取得今日/昨夜之生理恢復數據 (HRV、靜止心率、身體電量)
    優雅降級：若無數據或 API 拋出異常，一律安全回傳 None，絕不影響主任務。
    """
    if not target_date:
        target_date = datetime.date.today().isoformat()
    
    try:
        summary = {}
        hrv_data = {}
        try:
            summary = client.get_user_summary(target_date) or {}
        except Exception:
            pass
        
        try:
            hrv_data = client.get_hrv_data(target_date) or {}
        except Exception:
            pass
        
        # 若今日數據尚早未完全同步，嘗試檢索昨日摘要作為備援
        if not summary.get("restingHeartRate"):
            try:
                yest = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
                yest_summary = client.get_user_summary(yest) or {}
                if yest_summary.get("restingHeartRate"):
                    summary["restingHeartRate"] = yest_summary.get("restingHeartRate")
            except Exception:
                pass
                
        resting_hr = summary.get("restingHeartRate")
        body_batt = summary.get("bodyBatteryMostRecentValue") or summary.get("bodyBatteryHighestValue")
        
        hrv_summary = hrv_data.get("hrvSummary") or {}
        hrv_last_night = hrv_summary.get("lastNightAvg")
        hrv_weekly_avg = hrv_summary.get("weeklyAvg")
        hrv_status = hrv_summary.get("status")
        
        # 若所有指標皆為空，代表手錶未同步或未配戴入睡，回傳 None
        if not any([resting_hr, body_batt, hrv_last_night, hrv_weekly_avg]):
            return None
            
        return {
            "resting_hr": resting_hr,
            "body_battery": body_batt,
            "hrv_last_night": hrv_last_night,
            "hrv_weekly_avg": hrv_weekly_avg,
            "hrv_status": hrv_status
        }
    except Exception:
        return None
