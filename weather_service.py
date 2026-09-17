import requests

def get_open_meteo_weather(lat, lon, start_time_str):
    """根據經緯度與活動時間查詢 Open-Meteo 氣象數據"""
    try:
        if not start_time_str:
            return None
        clean_time = start_time_str.replace(" ", "T")[:13] + ":00"
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "weather_code"],
            "past_days": 7,
            "forecast_days": 1,
            "timezone": "auto"
        }
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            if clean_time in times:
                idx = times.index(clean_time)
            elif times:
                idx = -1
            else:
                return None
            
            temp = hourly.get("temperature_2m", [])[idx]
            rh = hourly.get("relative_humidity_2m", [])[idx]
            app_temp = hourly.get("apparent_temperature", [])[idx]
            w_code = hourly.get("weather_code", [])[idx]
            
            weather_desc = "晴" if w_code == 0 else "多雲/陰" if w_code in [1, 2, 3] else "雨" if w_code >= 51 else "陰"
            
            return {
                "temperature": temp,
                "humidity": rh,
                "apparent_temperature": app_temp,
                "weather_desc": weather_desc
            }
    except Exception as e:
        print(f"Open-Meteo 查詢異常: {e}")
    return None
