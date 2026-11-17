import requests
from utils import get_local_now


def _describe_wmo_code(w_code):
    """將 WMO 氣象代碼轉為簡明繁體中文天氣描述"""
    if w_code is None:
        return ""
    if w_code == 0:
        return "晴"
    if w_code in (1, 2, 3):
        return "多雲/陰"
    if w_code in (45, 48):
        return "霧"
    if w_code in (51, 53, 55, 56, 57):
        return "毛毛雨"
    if w_code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "雨"
    if w_code >= 95:
        return "雷雨"
    if w_code >= 71:
        return "雨夾雪/雪"
    return "陰"


def get_open_meteo_weather(lat, lon, start_time_str):
    """根據經緯度與活動時間查詢 Open-Meteo 歷史/當下氣象數據"""
    try:
        if not start_time_str:
            return None
        clean_time = start_time_str.replace(" ", "T")[:13] + ":00"
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "wind_speed_10m",
                "weather_code",
            ],
            "past_days": 7,
            "forecast_days": 1,
            "timezone": "auto"
        }
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            if clean_time not in times:
                return None
            idx = times.index(clean_time)

            temp = hourly.get("temperature_2m", [])[idx]
            rh = hourly.get("relative_humidity_2m", [])[idx]
            app_temp = hourly.get("apparent_temperature", [])[idx]
            wind_spd = (hourly.get("wind_speed_10m") or [None] * len(times))[idx]
            w_code = hourly.get("weather_code", [])[idx]

            return {
                "temperature": temp,
                "humidity": rh,
                "apparent_temperature": app_temp,
                "wind_speed": wind_spd,
                "weather_desc": _describe_wmo_code(w_code),
            }
    except Exception as e:
        print(f"Open-Meteo 查詢異常: {e}")
    return None


def get_today_weather_forecast(lat, lon):
    """取得今日關鍵跑步時段 (06:00 清晨 / 16:00 下午 / 20:00 晚間) 之氣象預報"""
    try:
        today_str = get_local_now().date().isoformat()
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation_probability",
                "wind_speed_10m",
                "weather_code",
            ],
            "forecast_days": 1,
            "timezone": "auto",
        }
        res = requests.get(url, params=params, timeout=5)
        if res.status_code != 200:
            return None

        hourly = res.json().get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return None

        target_slots = [
            ("清晨 (06:00)", f"{today_str}T06:00"),
            ("下午 (16:00)", f"{today_str}T16:00"),
            ("晚間 (20:00)", f"{today_str}T20:00"),
        ]

        slots = []
        for label, target_t in target_slots:
            if target_t not in times:
                continue
            idx = times.index(target_t)
            slots.append({
                "label": label,
                "temperature": hourly.get("temperature_2m", [None])[idx],
                "humidity": hourly.get("relative_humidity_2m", [None])[idx],
                "apparent_temperature": hourly.get("apparent_temperature", [None])[idx],
                "precip_prob": (hourly.get("precipitation_probability") or [None] * len(times))[idx],
                "wind_speed": (hourly.get("wind_speed_10m") or [None] * len(times))[idx],
                "weather_desc": _describe_wmo_code(hourly.get("weather_code", [None])[idx]),
            })
        return slots if slots else None
    except Exception as e:
        print(f"Open-Meteo 今日預報查詢異常: {e}")
        return None


def format_today_forecast(slots):
    """格式化今日訓練時段氣象預報為精簡報表區塊"""
    if not slots:
        return ""
    lines = ["🌤️ 【今日訓練時段氣象預報】"]
    for s in slots:
        parts = []
        if s.get("temperature") is not None:
            parts.append(f"{s['temperature']}°C")
        if s.get("apparent_temperature") is not None:
            parts.append(f"體感 {s['apparent_temperature']}°C")
        if s.get("humidity") is not None:
            parts.append(f"濕度 {s['humidity']}%")
        if s.get("precip_prob") is not None:
            parts.append(f"降雨 {s['precip_prob']}%")
        if s.get("wind_speed") is not None:
            parts.append(f"風速 {s['wind_speed']}km/h")
        if s.get("weather_desc"):
            parts.append(f"({s['weather_desc']})")
        if parts:
            lines.append(f"  - {s['label']}: {' | '.join(parts)}")
    return "\n".join(lines) if len(lines) > 1 else ""
