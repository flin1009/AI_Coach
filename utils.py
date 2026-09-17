import re
import datetime

def format_pace(speed_mps):
    """將公尺/秒轉換為每公里配速 (分:秒)"""
    if speed_mps <= 0:
        return "N/A"
    pace_sec = 1000 / speed_mps
    return f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"

def format_duration(seconds):
    """將秒數格式化為 時:分:秒 或 分:秒"""
    if seconds is None:
        return "0:00"
    total_sec = int(seconds)
    if total_sec < 3600:
        return f"{total_sec // 60}:{total_sec % 60:02d}"
    else:
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        return f"{h}:{m:02d}:{s:02d}"

def format_hr_zones(hr_zones_raw):
    """解析並格式化心率區間分佈 (Zone 1 ~ Zone 5)"""
    if not hr_zones_raw:
        return None
    items = hr_zones_raw if isinstance(hr_zones_raw, list) else hr_zones_raw.get("values", [])
    if not items:
        return None
    total_secs = sum(z.get("secsInZone", z.get("timeInZone", 0)) for z in items)
    if total_secs <= 0:
        return None
    parts = []
    for z in items:
        z_num = z.get("zoneNumber", z.get("zone"))
        secs = z.get("secsInZone", z.get("timeInZone", 0))
        if z_num is not None and secs > 0:
            pct = (secs / total_secs) * 100
            m = int(secs // 60)
            parts.append(f"Z{z_num}: {m}m({pct:.0f}%)")
    return " | ".join(parts) if parts else None

def clean_ai_text(text):
    """清理 AI 回覆中可能包含的 LaTeX 數學排版語法，轉為一般文字符號"""
    if not text:
        return text
    text = re.sub(r'\$?\\rightarrow\$?', '→', text)
    text = re.sub(r'\$?\\to\$?', '→', text)
    text = re.sub(r'\$?\\leftarrow\$?', '←', text)
    text = re.sub(r'\$?\\sim\$?', '~', text)
    return text

def format_activity_summary(a):
    """將一筆活動格式化為簡潔的一行摘要 (適用於歷史訓練脈絡清單)"""
    start_time = a.get("startTimeLocal", "")
    date_str = start_time[5:16] if len(start_time) >= 16 else start_time
    
    type_key = a.get("activityType", {}).get("typeKey", "workout").lower()
    if "running" in type_key or "treadmill" in type_key:
        type_name = "跑步"
    elif "cycling" in type_key or "bike" in type_key:
        type_name = "自行車"
    elif "swimming" in type_key or "pool" in type_key:
        type_name = "游泳"
    elif "strength" in type_key or "fitness" in type_key:
        type_name = "肌力/重訓"
    elif "walking" in type_key or "hiking" in type_key:
        type_name = "健行/步行"
    else:
        type_name = type_key

    s_dto = a.get("summaryDTO", {})
    dist = a.get("distance", 0) or 0
    duration = a.get("duration", 0) or 0
    avg_speed = a.get("averageSpeed", 0) or 0
    avg_hr = a.get("averageHR", 0)
    load = s_dto.get("activityTrainingLoad") or a.get("activityTrainingLoad")
    cals = a.get("calories", 0)

    parts = [f"{date_str}: {type_name} ({type_key})"]
    if dist > 0:
        parts.append(f"{dist/1000:.2f}km")
    if "running" in type_key and avg_speed > 0:
        parts.append(f"配速 {format_pace(avg_speed)}")
    elif duration > 0:
        parts.append(f"時間 {format_duration(duration)}")
    
    if avg_hr:
        parts.append(f"心率 {int(avg_hr)}bpm")
    if load:
        parts.append(f"負荷 {int(load)}")
    elif cals:
        parts.append(f"卡路里 {int(cals)}kcal")

    return " | ".join(parts)
 
def format_laps_table(laps):
    """將分圈資料排版為等寬代碼表格 (使用 <pre> 標籤以適配 Telegram Monospace 顯示)"""
    if not laps:
        return ""
    lines = []
    lines.append("<pre>")
    lines.append("圈數   配速   心率 步頻  時間")
    lines.append("---------------------------")
    for lap in laps:
        l_idx = lap.get("lapIndex", 0)
        l_pace = format_pace(lap.get("averageSpeed", 0))
        l_hr = int(lap.get("averageHR", 0))
        l_cad = int(lap.get("averageRunCadence", 0))
        l_time = format_duration(lap.get("duration", 0))
        lines.append(f"L{l_idx+1:02d}  {l_pace:>5}   {l_hr:>3}  {l_cad:>3} {l_time:>5}")
    lines.append("</pre>")
    return "\n".join(lines)

def check_activity_recency(start_time_str, max_hours=36):
    """檢查最新活動是否在指定小時內 (預設 36 小時)，並回傳 (is_recent, diff_hours)"""
    if not start_time_str:
        return False, 999.0
    try:
        clean_time = start_time_str.replace("T", " ")[:19]
        act_dt = datetime.datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()
        diff_hours = (now - act_dt).total_seconds() / 3600.0
        return diff_hours <= max_hours, diff_hours
    except Exception:
        return True, 0.0

def calculate_weekly_stats(activities):
    """統計近期活動的累積總跑量、總負荷與運動次數分佈"""
    total_run_dist_m = 0.0
    total_run_sec = 0.0
    total_load = 0.0
    run_count = 0
    cross_count = 0
    
    for a in activities:
        type_key = a.get("activityType", {}).get("typeKey", "").lower()
        s_dto = a.get("summaryDTO", {})
        dist = a.get("distance", 0) or 0
        dur = a.get("duration", 0) or 0
        load = s_dto.get("activityTrainingLoad") or a.get("activityTrainingLoad") or 0
        total_load += float(load)
        
        if "running" in type_key or "treadmill" in type_key:
            run_count += 1
            total_run_dist_m += float(dist)
            total_run_sec += float(dur)
        else:
            cross_count += 1
            
    return {
        "total_run_km": total_run_dist_m / 1000.0,
        "total_run_duration": format_duration(total_run_sec),
        "total_load": int(total_load),
        "run_count": run_count,
        "cross_count": cross_count,
        "total_activities": len(activities)
    }

def calculate_acwr(activities):
    """計算 ACWR (急性與慢性負荷比, Acute:Chronic Workload Ratio)
    - Acute Load (急性負荷): 過去 7 天的累積訓練負荷
    - Chronic Load (慢性負荷): 過去 28 天 (4 週) 的週平均負荷
    - 比值評估：
      < 0.8: 低負荷 / 減量恢復期 (Under-training)
      0.8 ~ 1.3: 最佳適應甜點區 (Sweet Spot, 受傷風險最低)
      1.31 ~ 1.49: 疲勞警戒期 (Caution)
      >= 1.50: 受傷高危險區 (Danger Zone)
    """
    if not activities:
        return {
            "acwr": 0.0,
            "acute_load": 0,
            "chronic_load": 0,
            "status_desc": "無運動數據",
            "status_zone": "none"
        }
    
    now = datetime.datetime.now()
    acute_cutoff = (now - datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    chronic_cutoff = (now - datetime.timedelta(days=28)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    acute_load = 0.0
    chronic_load_total = 0.0
    
    for a in activities:
        start_time_str = a.get("startTimeLocal", "")
        if not start_time_str:
            continue
        try:
            clean_time = start_time_str.replace("T", " ")[:19]
            act_dt = datetime.datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
            
        s_dto = a.get("summaryDTO", {})
        load = float(s_dto.get("activityTrainingLoad") or a.get("activityTrainingLoad") or 0)
        
        if act_dt >= acute_cutoff:
            acute_load += load
        if act_dt >= chronic_cutoff:
            chronic_load_total += load
            
    # 28 天 (4 週) 之週平均負荷
    chronic_load_weekly_avg = chronic_load_total / 4.0
    
    if chronic_load_weekly_avg <= 0:
        if acute_load > 0:
            acwr = 1.0
            status_desc = "初期建立 (基準累積中)"
            status_zone = "building"
        else:
            acwr = 0.0
            status_desc = "休整期 (無負荷)"
            status_zone = "rest"
    else:
        acwr = acute_load / chronic_load_weekly_avg
        if acwr < 0.8:
            status_desc = "低負荷 / 減量恢復期"
            status_zone = "under"
        elif acwr <= 1.3:
            status_desc = "最佳適應甜點區 (Sweet Spot)"
            status_zone = "optimal"
        elif acwr < 1.5:
            status_desc = "疲勞警戒期 (Caution)"
            status_zone = "caution"
        else:
            status_desc = "高受傷風險危險區 (Danger Zone)"
            status_zone = "danger"
            
    return {
        "acwr": round(acwr, 2),
        "acute_load": int(acute_load),
        "chronic_load": int(chronic_load_weekly_avg),
        "status_desc": status_desc,
        "status_zone": status_zone
    }

def format_recovery_metrics(recovery):
    """將生理恢復數據 (HRV/RHR/電量) 格式化為簡明文字"""
    if not recovery:
        return ""
    lines = ["🩺 【今日自律神經與生理恢復狀態】"]
    parts_1 = []
    if recovery.get("resting_hr"):
        parts_1.append(f"靜止心率: {recovery['resting_hr']} bpm")
    if recovery.get("body_battery"):
        parts_1.append(f"身體電量: {recovery['body_battery']}%")
    if parts_1:
        lines.append(f"  - {' | '.join(parts_1)}")
        
    parts_2 = []
    if recovery.get("hrv_last_night"):
        hrv_str = f"夜間 HRV: {recovery['hrv_last_night']} ms"
        extra = []
        if recovery.get("hrv_weekly_avg"):
            extra.append(f"7日均值 {recovery['hrv_weekly_avg']} ms")
        if recovery.get("hrv_status"):
            st_map = {"BALANCED": "均衡", "UNBALANCED": "失衡", "LOW": "偏低", "POOR": "不佳"}
            st_zh = st_map.get(recovery["hrv_status"], recovery["hrv_status"])
            extra.append(f"狀態: {st_zh}")
        if extra:
            hrv_str += f" ({' | '.join(extra)})"
        parts_2.append(hrv_str)
        
    if parts_2:
        lines.append(f"  - {' | '.join(parts_2)}")
        
    return "\n".join(lines) if len(lines) > 1 else ""

