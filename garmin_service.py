import datetime
from garminconnect import Garmin
from config import GARMIN_EMAIL, GARMIN_PWD

def get_garmin_client():
    """登入並回傳 Garmin 客戶端實例 (原方式：帳號密碼直接登入)"""
    if not GARMIN_EMAIL or not GARMIN_PWD:
        raise ValueError("找不到 GARMIN_EMAIL 或 GARMIN_PWD 環境變數")

    print("[Garmin] 正在透過帳號密碼連線 Garmin 登入...")
    client = Garmin(GARMIN_EMAIL, GARMIN_PWD)
    client.login()
    print("[Garmin] 登入成功！")
    return client


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
