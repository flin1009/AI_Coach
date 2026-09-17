import re

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
