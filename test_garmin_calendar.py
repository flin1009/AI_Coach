import os
import sys
import getpass
import datetime
from garminconnect import Garmin

def test_calendar():
    email = os.getenv("GARMIN_EMAIL")
    pwd = os.getenv("GARMIN_PWD")

    if not email:
        try:
            email = input("請輸入 Garmin Email: ").strip()
        except EOFError:
            pass
    if not pwd:
        try:
            pwd = getpass.getpass("請輸入 Garmin 密碼: ").strip()
        except EOFError:
            pass

    if not email or not pwd:
        print("❌ 未提供帳號密碼，無法登入 Garmin。")
        return

    print(f"🔐 正在連線登入 Garmin ({email})...")
    try:
        client = Garmin(email, pwd)
        client.login()
        print("✅ Garmin 登入成功！\n")
    except Exception as e:
        print(f"❌ 登入失敗: {e}")
        return

    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month

    # 查詢本月、下個月、下下個月 (跨月支援)
    target_months = []
    for offset in [0, 1, 2]:
        m = current_month + offset
        y = current_year
        if m > 12:
            m -= 12
            y += 1
        target_months.append((y, m))

    print(f"📅 準備查詢行事曆月份: {[f'{y}/{m:02d}' for y, m in target_months]}")
    print("=" * 60)

    all_events = []
    all_workouts = []
    raw_samples = []

    for y, m in target_months:
        print(f"\n🔍 正在抓取 {y} 年 {m} 月的行事曆資料...")
        try:
            data = client.get_scheduled_workouts(y, m)
            items = data.get("calendarItems", []) if isinstance(data, dict) else []
            print(f"  ↳ 共取得 {len(items)} 筆日曆項目")

            # 分析日曆項目的類型分佈
            type_counts = {}
            for item in items:
                itype = item.get("itemType", "unknown")
                type_counts[itype] = type_counts.get(itype, 0) + 1

                if itype in ["event", "race"] or "event" in str(itype).lower():
                    all_events.append(item)
                elif itype == "workout":
                    all_workouts.append(item)
                
                # 保留非 activity 的樣本觀察結構
                if itype != "activity" and len(raw_samples) < 5:
                    raw_samples.append(item)

            print(f"  ↳ 項目類型分佈: {type_counts}")

        except Exception as e:
            print(f"  ❌ 抓取 {y}/{m} 失敗: {e}")

    print("\n" + "=" * 60)
    print("🏆 【目標賽事 (Target Races / Events) 檢驗結果】")
    print("=" * 60)

    if all_events:
        print(f"🎉 成功找到 {len(all_events)} 場目標賽事 / 事件：\n")
        for idx, ev in enumerate(all_events, 1):
            title = ev.get("title") or ev.get("eventTitle") or ev.get("name") or "未命名賽事"
            date = ev.get("date") or ev.get("startDate") or "未知日期"
            item_type = ev.get("itemType")
            dist = ev.get("distance")
            dist_str = f"{dist/1000:.2f} km" if dist else "未設定距離"
            
            print(f"  [{idx}] 賽事名稱: {title}")
            print(f"      日期: {date}")
            print(f"      距離: {dist_str}")
            print(f"      類型: {item_type}")
            print(f"      詳細數據: {ev}")
            print("-" * 50)
    else:
        print("ℹ️ 在這幾個月的行事曆中，目前沒有標記為 'event' 的賽事。")

    print("\n" + "=" * 60)
    print("🏃 【預定訓練課表 (Scheduled Workouts) 檢驗結果】")
    print("=" * 60)
    if all_workouts:
        print(f"共找到 {len(all_workouts)} 個預定課表：")
        for w in all_workouts[:5]:
            title = w.get("title") or w.get("workoutName") or "未命名課表"
            date = w.get("date") or "未知日期"
            print(f"  - [{date}] {title}")
    else:
        print("ℹ️ 目前沒有排定未來的訓練課表。")

    if raw_samples and not all_events:
        print("\n" + "=" * 60)
        print("🔍 【其他非活動項目結構範例】")
        print("=" * 60)
        for s in raw_samples:
            print(f"  - {s.get('itemType')}: {s}")

if __name__ == "__main__":
    test_calendar()
