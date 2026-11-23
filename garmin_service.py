import base64
import datetime
import json
import os
from garminconnect import Garmin
from config import GARMIN_EMAIL, GARMIN_PWD, GARMIN_TOKENS
from utils import get_local_now


def _normalize_tokenstore(raw_token):
    """將 GARMINTOKENS 正規化為 garminconnect 可識別的 JSON 字串或路徑（兼容 raw JSON 與 Base64）"""
    if not raw_token:
        return None
    token = raw_token.strip()
    if not token:
        return None
    if token.startswith("{"):
        return token
    if os.path.exists(os.path.expanduser(token)):
        return token
    try:
        decoded = base64.b64decode(token, validate=True).decode("utf-8").strip()
        if decoded.startswith("{"):
            json.loads(decoded)
            return decoded
    except Exception:
        pass
    return token


def get_garmin_client():
    """登入並回傳 Garmin 客戶端實例（優先以 GARMINTOKENS 登入，失敗或未設定時退回帳號密碼登入）"""
    tokenstore = _normalize_tokenstore(GARMIN_TOKENS)
    has_credentials = bool(GARMIN_EMAIL and GARMIN_PWD)

    if not tokenstore and not has_credentials:
        raise ValueError("找不到 GARMINTOKENS 或 GARMIN_EMAIL / GARMIN_PWD 環境變數")

    if tokenstore:
        print("[Garmin] 偵測到 GARMINTOKENS，優先嘗試透過 OAuth Token 連線登入...")
        try:
            client = Garmin(GARMIN_EMAIL, GARMIN_PWD)
            client.login(tokenstore)
            print("[Garmin] 登入成功！")
            return client
        except Exception as token_err:
            if not has_credentials:
                raise
            print(f"⚠️ [Garmin] OAuth Token 登入失敗 ({token_err})，自動降級為帳號密碼登入...")
            # 暫時移除環境變數中的 GARMINTOKENS，避免 Garmin.login() 重讀無效 Token
            prev_env_token = os.environ.pop("GARMINTOKENS", None)
            try:
                client = Garmin(GARMIN_EMAIL, GARMIN_PWD)
                client.login()
                print("[Garmin] 帳號密碼備援登入成功！")
                return client
            finally:
                if prev_env_token is not None:
                    os.environ["GARMINTOKENS"] = prev_env_token

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

def fetch_extended_activities(client, count=35, days=28):
    """取得過去指定天數 (預設 28 天) 的長週期活動數據，供 ACWR 模型完整計算。
    優先使用日期區間查詢避免高頻交叉訓練截斷 28 天視窗，失敗時優雅降級為筆數查詢。
    """
    try:
        end_date = get_local_now().date()
        start_date = end_date - datetime.timedelta(days=days)
        by_date = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())
        if isinstance(by_date, list):
            return by_date
    except Exception as e:
        print(f"⚠️ 日期區間查詢長週期活動失敗 (改用筆數查詢): {e}")

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
        tw_today = get_local_now().date()
        target_date = tw_today.isoformat()
    
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
                tw_today = get_local_now().date()
                yest = (tw_today - datetime.timedelta(days=1)).isoformat()
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

def fetch_upcoming_races(client, months_ahead=3, days_back=0):
    """取得未來指定月數內 (預設3個月/90天) 的目標賽事清單，並依日期去重排序
    - 支援透過 days_back 回溯過去數日 (例如 days_back=1 供昨日活動關聯前一天賽事，包含跨月初情境)
    - 解決跨月日曆網格導致同賽事重複出現的問題 (依據 item.id 唯一性去重)
    - 嚴格過濾 (today - days_back) 至 (today + 90天) 內的賽事
    - 計算倒數天數 (days_left；昨日為 -1，今日為 0) 與賽事距離 (公里)
    - 優雅降級：若 API 連線失敗或無資料，安全回傳空清單 []
    """
    try:
        today = get_local_now().date()
        min_date = today - datetime.timedelta(days=days_back)
        max_date = today + datetime.timedelta(days=months_ahead * 30)

        # 計算欲查詢的年月份 (涵蓋 min_date 所屬月份至未來 months_ahead 個月，避免跨月初漏抓昨日賽事)
        target_months = []
        seen_months = set()

        def _add_month(y, m):
            if (y, m) not in seen_months:
                seen_months.add((y, m))
                target_months.append((y, m))

        cur_y, cur_m = min_date.year, min_date.month
        while (cur_y, cur_m) <= (today.year, today.month):
            _add_month(cur_y, cur_m)
            cur_m += 1
            if cur_m > 12:
                cur_m = 1
                cur_y += 1

        for offset in range(months_ahead + 1):
            m = today.month + offset
            y = today.year
            if m > 12:
                y += (m - 1) // 12
                m = ((m - 1) % 12) + 1
            _add_month(y, m)

        seen_ids = set()
        races = []

        for y, m in target_months:
            try:
                data = client.get_scheduled_workouts(y, m)
                items = data.get("calendarItems", []) if isinstance(data, dict) else []
                for item in items:
                    itype = str(item.get("itemType", "")).lower()
                    if itype not in ["event", "race"] and "event" not in itype:
                        continue

                    # 唯一性 ID 去重 (防止日曆前後跨月重複)
                    item_id = item.get("id") or item.get("eventId") or (item.get("date"), item.get("title"))
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    date_str = item.get("date") or item.get("startDate")
                    if not date_str:
                        continue
                    
                    try:
                        # 擷取 YYYY-MM-DD 部分
                        clean_date_str = date_str[:10]
                        race_date = datetime.date.fromisoformat(clean_date_str)
                    except Exception:
                        continue

                    # 僅保留檢索區間內的賽事 (預設 today 起算；若指定 days_back 則一併帶出昨日賽事)
                    if min_date <= race_date <= max_date:
                        days_left = (race_date - today).days
                        dist_meters = item.get("distance")
                        dist_km = round(dist_meters / 1000.0, 1) if dist_meters else None
                        title = item.get("title") or item.get("eventTitle") or item.get("name") or "未命名賽事"

                        races.append({
                            "id": item.get("id"),
                            "title": title,
                            "date": clean_date_str,
                            "days_left": days_left,
                            "distance_km": dist_km,
                            "completion_target": item.get("completionTarget")
                        })
            except Exception as month_err:
                print(f"⚠️ 讀取 {y}/{m} 行事曆失敗: {month_err}")
                continue

        # 按賽事日期由近到遠排序
        races.sort(key=lambda r: r["date"])
        return races
    except Exception as e:
        print(f"⚠️ 取得目標賽事發生異常: {e}")
        return []
