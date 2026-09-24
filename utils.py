import re
import datetime
import math

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
    """格式化分圈細節清單 (原方式：純文字清單，無任何 HTML 標籤，保證相容所有裝置)"""
    if not laps:
        return ""
    lines = ["[分圈細節 (配速 | 心率 | 海拔上升 | 步頻 | 總時間)]"]
    for lap in laps:
        l_idx = lap.get("lapIndex", 0)
        l_pace = format_pace(lap.get("averageSpeed", 0))
        l_hr = int(lap.get("averageHR", 0))
        l_elev = int(lap.get("elevationGain", 0))
        l_cad = int(lap.get("averageRunCadence", 0))
        l_time = format_duration(lap.get("duration", 0))
        lines.append(f"  - L{l_idx+1:02d}: {l_pace} | {l_hr}bpm | {l_elev}m | {l_cad}spm | {l_time}")
    return "\n".join(lines)

def check_activity_recency(start_time_str, max_hours=26):
    """檢查最新活動是否在指定小時內 (預設 26 小時，適用於每日固定清晨排程判讀前晚訓練)，並回傳 (is_recent, diff_hours)"""
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

# --- 丹尼爾博士 VDOT 跑力與靶心配速系統 (Jack Daniels' Running Formula) ---

def parse_marathon_pb(pb_str):
    """解析馬拉松成績字串 (支援 H:MM 與 H:MM:SS) 為總分鐘數"""
    if not pb_str:
        return 225.0
    try:
        parts = [int(p) for p in pb_str.strip().split(":")]
        if len(parts) == 2:
            return parts[0] * 60.0 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 60.0 + parts[1] + parts[2] / 60.0
    except Exception:
        pass
    return 225.0

def calculate_vdot(distance_m, time_minutes):
    """依據 Daniels & Gilbert (1979) 攝氧量阻力公式計算 VDOT 跑力值"""
    if time_minutes <= 0 or distance_m <= 0:
        return 40.0
    v = distance_m / time_minutes  # m/min
    vo2 = -4.60 + 0.182258 * v + 0.000104 * (v ** 2)
    p = 0.8 + 0.1894393 * math.exp(-0.012778 * time_minutes) + 0.2989558 * math.exp(-0.1932605 * time_minutes)
    return vo2 / p

def vdot_to_pace(vdot, intensity_fraction):
    """依指定 VDOT 強度百分比反解配速 (分:秒/km)"""
    target_vo2 = vdot * intensity_fraction
    a = 0.000104
    b = 0.182258
    c = -(4.60 + target_vo2)
    discriminant = b ** 2 - 4 * a * c
    if discriminant < 0:
        return "N/A"
    v = (-b + math.sqrt(discriminant)) / (2 * a)  # m/min
    if v <= 0:
        return "N/A"
    sec_per_km = 60000.0 / v
    m = int(sec_per_km // 60)
    s = int(round(sec_per_km % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"

def calculate_vdot_paces(pb_str):
    """計算跑者全馬 PB 之 VDOT 跑力及五大丹尼爾訓練靶心配速 (E/M/T/I/R)"""
    time_min = parse_marathon_pb(pb_str)
    vdot = calculate_vdot(42195, time_min)
    return {
        "vdot": round(vdot, 1),
        "e_pace_fast": vdot_to_pace(vdot, 0.74),  # 有氧輕鬆跑上限 (~74% VDOT)
        "e_pace_slow": vdot_to_pace(vdot, 0.65),  # 有氧輕鬆跑下限 (~65% VDOT)
        "m_pace": vdot_to_pace(vdot, 0.80),       # 馬拉松配速 (~80% VDOT)
        "t_pace": vdot_to_pace(vdot, 0.88),       # 乳酸閾值/節奏 (~88% VDOT)
        "i_pace": vdot_to_pace(vdot, 0.98),       # 最大攝氧量間歇 (~98% VDOT)
        "r_pace": vdot_to_pace(vdot, 1.08),       # 重複衝刺/神經速度 (~108% VDOT)
    }

def format_vdot_paces(vdot_data):
    """格式化 VDOT 靶心配速為精簡單行摘要"""
    if not vdot_data:
        return ""
    return (
        f"🎯 【VDOT {vdot_data['vdot']} 靶心配速】"
        f"E {vdot_data['e_pace_fast']}~{vdot_data['e_pace_slow']} | "
        f"M {vdot_data['m_pace']} | "
        f"T {vdot_data['t_pace']} | "
        f"I {vdot_data['i_pace']} | "
        f"R {vdot_data['r_pace']}"
    )

# --- 前後半程有氧解耦率 (Aerobic Decoupling / Decoupling %) ---

def calculate_aerobic_decoupling(laps):
    """計算前半程 vs 後半程之有氧解耦率 (Decoupling %)
    - 採用 Joe Friel 效率因子 EF (Efficiency Factor) 公式：
      有功率時: EF = 平均功率 (W) / 平均心率 (bpm)
      無功率時: EF = 配速速度 (m/min) / 平均心率 (bpm)
    - Decoupling % = ((EF_前半 - EF_後半) / EF_前半) * 100%
    - 評級標準：
      < 3.0%: 極度穩定 (Elite Aerobic Base, 幾無心率漂移)
      3.0% ~ 5.0%: 最佳適應 (Well-Trained, 心率配速穩定平衡)
      5.1% ~ 8.0%: 輕度漂移 (Moderate Drift, 需留意補水散熱)
      > 8.0%: 顯著解耦 (High Drift, 體能超載或嚴重脫水)
    """
    if not laps or len(laps) < 2:
        return None

    total_dist = sum(lap.get("distance", 0) for lap in laps)
    total_dur = sum(lap.get("duration", 0) for lap in laps)

    # 至少 3 公里且總耗時大於 15 分鐘，數據方具統計學診斷意義
    if total_dist < 3000 and total_dur < 900:
        return None

    half_dist = total_dist / 2.0
    accum_dist = 0.0

    first_half_laps = []
    second_half_laps = []

    for lap in laps:
        d = lap.get("distance", 0)
        if accum_dist + d / 2.0 <= half_dist:
            first_half_laps.append(lap)
        else:
            second_half_laps.append(lap)
        accum_dist += d

    if not first_half_laps or not second_half_laps:
        mid = len(laps) // 2
        first_half_laps = laps[:mid]
        second_half_laps = laps[mid:]

    def get_half_ef(half_laps):
        total_d = sum(l.get("distance", 0) for l in half_laps)
        total_t = sum(l.get("duration", 0) for l in half_laps)
        if total_t <= 0 or total_d <= 0:
            return None, 0, 0, False

        avg_speed = total_d / total_t  # m/s
        total_hr_dur = sum(l.get("averageHR", 0) * l.get("duration", 0) for l in half_laps if l.get("averageHR"))
        hr_dur_weight = sum(l.get("duration", 0) for l in half_laps if l.get("averageHR"))
        avg_hr = (total_hr_dur / hr_dur_weight) if hr_dur_weight > 0 else 0

        has_power = any(l.get("avgPower") for l in half_laps)
        if has_power:
            p_dur = sum(l.get("avgPower", 0) * l.get("duration", 0) for l in half_laps if l.get("avgPower"))
            p_weight = sum(l.get("duration", 0) for l in half_laps if l.get("avgPower"))
            avg_p = (p_dur / p_weight) if p_weight > 0 else 0
            ef = avg_p / avg_hr if avg_hr > 0 else 0
            return ef, avg_p, avg_hr, True
        else:
            speed_mpm = avg_speed * 60.0
            ef = speed_mpm / avg_hr if avg_hr > 0 else 0
            return ef, avg_speed, avg_hr, False

    ef1, val1, hr1, is_pwr = get_half_ef(first_half_laps)
    ef2, val2, hr2, _ = get_half_ef(second_half_laps)

    if not ef1 or not ef2 or ef1 <= 0:
        return None

    decoupling_pct = ((ef1 - ef2) / ef1) * 100.0

    if decoupling_pct < 3.0:
        status_desc = "極度穩定 (Elite Aerobic Base, 幾無心率漂移)"
        status_zone = "excellent"
    elif decoupling_pct <= 5.0:
        status_desc = "最佳適應 (Well-Trained, 心率配速穩定平衡)"
        status_zone = "optimal"
    elif decoupling_pct <= 8.0:
        status_desc = "輕度漂移 (Moderate Drift, 需留意補水散熱)"
        status_zone = "warning"
    else:
        status_desc = "顯著解耦 (High Drift, 體能超載或嚴重脫水)"
        status_zone = "danger"

    return {
        "decoupling_pct": round(decoupling_pct, 1),
        "ef1": round(ef1, 2),
        "ef2": round(ef2, 2),
        "hr1": int(round(hr1)),
        "hr2": int(round(hr2)),
        "val1": round(val1, 1),
        "val2": round(val2, 1),
        "is_power": is_pwr,
        "status_desc": status_desc,
        "status_zone": status_zone
    }

def format_aerobic_decoupling(decoupling_data):
    """將有氧解耦率格式化為易讀報告文字"""
    if not decoupling_data:
        return ""
    d_pct = decoupling_data["decoupling_pct"]
    sign = "+" if d_pct > 0 else ""
    lines = [
        "💓 【有氧解耦率 (Aerobic Decoupling / 前後半程心率漂移)】",
        f"  - 前半程 vs 後半程心率: {decoupling_data['hr1']} bpm → {decoupling_data['hr2']} bpm",
        f"  - 解耦漂移率: {sign}{d_pct}% ({decoupling_data['status_desc']})"
    ]
    return "\n".join(lines)

def format_upcoming_races(races):
    """格式化未來三個月內之目標賽事清單與倒數"""
    if not races:
        return ""
    lines = ["🏆 【未來目標賽事 (近三個月倒數)】"]
    for r in races:
        days = r.get("days_left", 0)
        dist = r.get("distance_km")
        dist_str = f" | {dist}km" if dist else ""
        weeks = days // 7
        if days == 0:
            time_str = "🔥 今天比賽日 (Race Day!)"
        elif days == 1:
            time_str = "⚡ 明天比賽日 (Tomorrow!)"
        elif days < 14:
            time_str = f"倒數 {days} 天"
        else:
            time_str = f"倒數 {days} 天 (約 {weeks} 週)"
        lines.append(f"  - 🚩 {r['date']} ({time_str}) {r['title']}{dist_str}")
    return "\n".join(lines)


