from garminconnect import Garmin
from config import GARMIN_EMAIL, GARMIN_PWD

def get_garmin_client():
    """登入並回傳 Garmin 客戶端實例"""
    if not GARMIN_EMAIL or not GARMIN_PWD:
        raise ValueError("找不到 GARMIN_EMAIL 或 GARMIN_PWD 環境變數")
    client = Garmin(GARMIN_EMAIL, GARMIN_PWD)
    client.login()
    return client

def fetch_recent_activities(client, count=3):
    """取得近期運動活動"""
    try:
        return client.get_activities(0, count)
    except Exception as e:
        print(f"❌ 取得 Garmin 活動失敗: {e}")
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
