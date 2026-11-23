import datetime
import os
import sys
import time
from config import (
    ACTIVITIES_COUNT,
    DEFAULT_LAT,
    DEFAULT_LON,
    RUNNER_NAME,
    RUNNER_BIRTH_YEAR,
    RUNNER_PB,
    ZONE2_MAX_HR,
    LOCAL_SAVE_DIR
)
from utils import (
    get_local_now,
    format_pace,
    format_duration,
    format_hr_zones,
    clean_ai_text,
    format_activity_summary,
    format_laps_table,
    select_yesterday_activity,
    calculate_weekly_stats,
    calculate_rolling_mileage,
    calculate_acwr,
    format_recovery_metrics,
    calculate_vdot_paces,
    format_vdot_paces,
    calculate_aerobic_decoupling,
    format_aerobic_decoupling,
    format_upcoming_races,
    format_yesterday_races,
    format_recent_races,
    format_yesterday_race_context
)
from weather_service import (
    get_open_meteo_weather,
    get_today_weather_forecast,
    format_today_forecast
)
from notifier import send_telegram, send_telegram_photo
from garmin_service import (
    get_garmin_client,
    fetch_recent_activities,
    fetch_extended_activities,
    fetch_activity_splits,
    fetch_activity_hr_zones,
    fetch_daily_recovery_metrics,
    fetch_upcoming_races
)
from ai_service import (
    get_genai_client,
    detect_candidate_models,
    generate_coach_advice,
    generate_rest_day_advice
)
from chart_service import generate_all_telemetry_charts

def _format_ai_section(section_title, ai_advice, used_model, best_model):
    """組裝 AI 教練建議區塊，並在標題下方備註實際使用的 AI 模型"""
    display_used = used_model.replace("models/", "") if used_model else "unknown"
    display_best = best_model.replace("models/", "") if best_model else "unknown"
    if used_model and used_model != best_model and used_model != "fallback-rule-engine":
        model_note = f"(🤖 使用模型：{display_used}，由 {display_best} 容錯切換)"
    else:
        model_note = f"(🤖 使用模型：{display_used})"
    return f"\n\n{section_title}\n{model_note}\n{ai_advice}"


def _format_acwr_lines(acwr_data, mileage_data):
    """組裝 ACWR 負荷與 7/28 日跑量監控區塊"""
    return [
        "📈 【ACWR 急性與慢性負荷監控 (截至昨日，近28日)】",
        f"  - ACWR 比值: {acwr_data['acwr']} ({acwr_data['status_desc']})",
        f"  - 急性負荷 (近7日): {acwr_data['acute_load']} | 慢性負荷 (28日週均): {acwr_data['chronic_load']}",
        f"  - 跑量統計: 近7日 {mileage_data['run_km_7d']:.2f} km ({mileage_data['run_count_7d']} 趟) | 近28日週均 {mileage_data['run_km_28d_weekly_avg']:.2f} km",
        "-" * 30,
    ]


def run_main_task():
    # 1. 初始化 AI 客戶端與模型
    ai_client = get_genai_client()
    candidate_models = detect_candidate_models(ai_client)
    best_model = candidate_models[0]

    try:
        # 2. 初始化 Garmin 客戶端並取得活動
        client_garmin = get_garmin_client()
        activities = fetch_recent_activities(client_garmin, ACTIVITIES_COUNT)
        
        if not activities:
            print("📭 沒有找到近期活動")
            return

        # 3. 取得長週期活動 (28天) 與今日生理指標 (優雅降級)
        local_now = get_local_now()
        extended_activities = fetch_extended_activities(client_garmin, count=35)
        long_window_acts = extended_activities if extended_activities else activities
        acwr_data = calculate_acwr(long_window_acts, reference_now=local_now)
        mileage_data = calculate_rolling_mileage(long_window_acts, reference_now=local_now)
        print(f"📈 ACWR 負荷比計算: {acwr_data['acwr']} ({acwr_data['status_desc']}) | 急性: {acwr_data['acute_load']} | 慢性: {acwr_data['chronic_load']} | 7日跑量: {mileage_data['run_km_7d']:.2f}km")

        # 計算丹尼爾 VDOT 跑力與五大訓練靶心配速
        vdot_data = calculate_vdot_paces(RUNNER_PB)
        vdot_str = format_vdot_paces(vdot_data)
        print(f"🎯 丹尼爾 VDOT 跑力計算: VDOT {vdot_data['vdot']} | E: {vdot_data['e_pace_fast']}~{vdot_data['e_pace_slow']} | M: {vdot_data['m_pace']} | T: {vdot_data['t_pace']}")

        recovery_metrics = fetch_daily_recovery_metrics(client_garmin)
        recovery_str = format_recovery_metrics(recovery_metrics)
        if recovery_str:
            print(f"🩺 成功取得今日生理恢復數據: RHR={recovery_metrics.get('resting_hr')}bpm, HRV={recovery_metrics.get('hrv_last_night')}ms")
        else:
            print("ℹ️ 今日無生理恢復數據 (手錶未同步或未配戴入睡)，優雅略過此區塊。")

        # 4. 取得未來目標賽事 (近三個月/90天)、昨日賽事 (D-1) 與近7日剛完賽賽事 (D-2~D-7)
        all_races = fetch_upcoming_races(client_garmin, months_ahead=3, days_back=7)
        yesterday_races = [r for r in all_races if r.get("days_left", 0) == -1]
        recent_races = [r for r in all_races if -7 <= r.get("days_left", 0) <= -2]
        upcoming_races = [r for r in all_races if r.get("days_left", 0) >= 0]
        races_str = format_upcoming_races(upcoming_races)
        yesterday_races_str = format_yesterday_races(yesterday_races)
        recent_races_str = format_recent_races(recent_races)
        if yesterday_races:
            print(f"🏁 偵測到昨日目標賽事日: {', '.join(r['title'] for r in yesterday_races)}")
        if recent_races:
            print(f"🏁 偵測到近7日剛完賽賽事: {', '.join(r['title'] for r in recent_races)}")
        if races_str:
            print(f"🏆 成功取得近期目標賽事: {len(upcoming_races)} 場")
        else:
            print("ℹ️ 近期三個月內未排定目標賽事。")

        # 5. 計算本地時間基準 (今日報告日 vs 昨日分析標的日) 並取得今日時段氣象預報
        today_date = local_now.date()
        yesterday_date = today_date - datetime.timedelta(days=1)
        weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
        today_label = f"{today_date.isoformat()} ({weekday_names[today_date.weekday()]})"
        yesterday_label = f"{yesterday_date.isoformat()} ({weekday_names[yesterday_date.weekday()]})"

        today_forecast = get_today_weather_forecast(DEFAULT_LAT, DEFAULT_LON)
        today_forecast_str = format_today_forecast(today_forecast)
        if today_forecast_str:
            today_forecast_str = today_forecast_str.replace(
                "🌤️ 【今日訓練時段氣象預報】",
                f"🌤️ 【今日訓練時段氣象預報 ({today_label})】",
            )

        activity_pool = list(activities) + list(extended_activities or [])
        primary_act, other_yesterday_acts, history_acts, diff_hours = select_yesterday_activity(
            activity_pool, reference_now=local_now
        )
        display_history = history_acts[:ACTIVITIES_COUNT]

        # 若昨日 (D-1) 無任何運動紀錄，自動切換為【昨日休整與今日恢復日報】模式
        if primary_act is None:
            print(f"🌿 昨日 ({yesterday_label}) 無運動紀錄 (前次訓練距今約 {diff_hours:.1f} 小時)，切換為【昨日休整與今日恢復日報】模式...")
            days_ago = int(diff_hours // 24)
            hours_ago = int(diff_hours % 24)
            time_ago_str = f"{days_ago} 天 {hours_ago} 小時前" if days_ago > 0 else f"{hours_ago} 小時前"
            
            stats = calculate_weekly_stats(display_history)
            
            report = []
            rest_title_tpl = f"🌿 【{RUNNER_NAME} 昨日休整與今日恢復日報 - {{model}}】"
            report.append(rest_title_tpl.format(model=best_model))
            report.append(f"📅 報告日期：{today_label} | 分析標的：昨日 {yesterday_label}")
            report.append(f"背景：{RUNNER_BIRTH_YEAR}年生 | PB {RUNNER_PB} | Zone 2: {ZONE2_MAX_HR}bpm")
            report.append(f"狀態：昨日 {yesterday_label} 無運動紀錄（前次訓練於 {time_ago_str}）")
            report.append("=" * 30)

            if vdot_str:
                report.append(vdot_str)
                report.append("-" * 30)

            if yesterday_races_str:
                report.append(yesterday_races_str)
                report.append("-" * 30)

            if recent_races_str:
                report.append(recent_races_str)
                report.append("-" * 30)

            if races_str:
                report.append(races_str)
                report.append("-" * 30)

            if recovery_str:
                report.append(recovery_str)
                report.append("-" * 30)

            if today_forecast_str:
                report.append(today_forecast_str)
                report.append("-" * 30)

            report.extend(_format_acwr_lines(acwr_data, mileage_data))
            
            report.append(f"📊 【近期累積運動統計 (截至昨日，近 {stats['total_activities']} 筆)】")
            report.append(f"  - 累積總跑量: {stats['total_run_km']:.2f} km")
            report.append(f"  - 跑步總耗時: {stats['total_run_duration']}")
            report.append(f"  - 累積總負荷: {stats['total_load']}")
            report.append(f"  - 訓練次數: {stats['run_count']} 次跑步 / {stats['cross_count']} 次交叉訓練")
            report.append("-" * 30)
            
            report.append(f"📋 【近期訓練歷程明細 (截至昨日 {yesterday_label})】")
            for act in display_history:
                summary_line = format_activity_summary(act)
                report.append(f"  - {summary_line}")
            report.append("=" * 30)
            
            full_text = "\n".join(report)
            print("🤖 正在諮詢 Gemini AI 休整與超補償建議...")
            ai_advice, used_model = generate_rest_day_advice(ai_client, candidate_models, full_text)
            
            if used_model != best_model:
                full_text = full_text.replace(rest_title_tpl.format(model=best_model), rest_title_tpl.format(model=used_model))
            
            final_message = clean_ai_text(
                full_text + _format_ai_section("🤖 【Gemini 休整與超補償指引】", ai_advice, used_model, best_model)
            )
            
            send_telegram(final_message)

            # 生成並推播休整圖表 (各圖表獨立分開，大字體高清晰)
            print("📊 正在產出休整與 ACWR 負荷圖表...")
            charts = generate_all_telemetry_charts(
                None, None, acwr_data, None, output_dir=LOCAL_SAVE_DIR, date_label=f"截至昨日 {yesterday_date.isoformat()}"
            )
            for c_path, c_caption in charts:
                send_telegram_photo(c_path, caption=c_caption)
                time.sleep(0.5)

            print(f"✅ 今日休整任務完成：{get_local_now()}")
            return

        # 4. 組裝報表抬頭 (昨日活動分析 + 今日訓練計畫模式)
        report = []
        active_title_tpl = f"📊 【{RUNNER_NAME} 每日訓練分析報表 - {{model}}】"
        report.append(active_title_tpl.format(model=best_model))
        report.append(f"📅 報告日期：{today_label} | 分析標的：昨日 {yesterday_label}")
        report.append(f"背景：{RUNNER_BIRTH_YEAR}年生 | PB {RUNNER_PB} | Zone 2: {ZONE2_MAX_HR}bpm")
        report.append("=" * 30)

        if vdot_str:
            report.append(vdot_str)
            report.append("-" * 30)

        if recent_races_str:
            report.append(recent_races_str)
            report.append("-" * 30)

        if races_str:
            report.append(races_str)
            report.append("-" * 30)

        if recovery_str:
            report.append(recovery_str)
            report.append("-" * 30)

        if today_forecast_str:
            report.append(today_forecast_str)
            report.append("-" * 30)

        report.extend(_format_acwr_lines(acwr_data, mileage_data))

        # 5. 近期訓練脈絡 (截至昨日之歷程簡要列表) 與昨日賽事判定
        is_yesterday_race, yesterday_race_note = format_yesterday_race_context(primary_act, yesterday_races)
        report.append(f"📋 【近期訓練歷程 (截至昨日，近 {len(display_history)} 筆摘要)】")
        for act in display_history:
            if act is primary_act:
                tag = " [昨日主分析 | 正式賽事]" if is_yesterday_race else " [昨日主分析]"
            else:
                tag = ""
            summary_line = format_activity_summary(act)
            report.append(f"  - {summary_line}{tag}")
        report.append("-" * 30)

        # 5. 昨日主要活動深度解剖
        latest_act = primary_act
        a_id = latest_act["activityId"]
        s_dto = latest_act.get('summaryDTO', {})
        
        entry = f"🏃 【昨日活動深度數據 ({yesterday_label})】"
        if yesterday_race_note:
            entry += f"\n{yesterday_race_note}"
        if latest_act.get("activityName"):
            entry += f"\n🏷️ 名稱: {latest_act.get('activityName')}"
        entry += f"\n📍 地點: {latest_act.get('locationName', 'Unknown')}"
        entry += f"\n📅 日期: {latest_act.get('startTimeLocal')}"
        entry += f"\n類型: {latest_act.get('activityType', {}).get('typeKey')} | 距離: {latest_act.get('distance', 0)/1000:.2f}km | 卡路里: {int(latest_act.get('calories', 0))} kcal"
        entry += f"\n時間: 移動 {latest_act.get('movingDuration',0)/60:.1f}m / 總計 {latest_act.get('duration',0)/60:.1f}m"
        entry += f"\n配速: 平均 {format_pace(latest_act.get('averageSpeed',0))} | 最佳 {format_pace(latest_act.get('maxSpeed',0))}"
        entry += f"\n心率: 平均 {latest_act.get('averageHR',0)} | 最大 {latest_act.get('maxHR',0)} bpm"
        
        # 跑步功率 (Power)
        avg_p = s_dto.get('avgPower') or latest_act.get('avgPower')
        max_p = s_dto.get('maxPower') or latest_act.get('maxPower')
        if avg_p:
            p_str = f"\n功率: 平均 {int(avg_p)}W"
            if max_p:
                p_str += f" | 最大 {int(max_p)}W"
            entry += p_str
        
        # 步頻 (Cadence)
        avg_cad = s_dto.get('averageRunCadence') or latest_act.get('averageRunCadence')
        max_cad = s_dto.get('maxRunCadence') or latest_act.get('maxRunCadence')
        if avg_cad:
            c_str = f"\n步頻: 平均 {int(avg_cad)}spm"
            if max_cad:
                c_str += f" | 最大 {int(max_cad)}spm"
            entry += c_str
        
        # 進階跑步動態 (Running Dynamics)
        stride = s_dto.get('strideLength') or latest_act.get('strideLength')
        vo = s_dto.get('verticalOscillation') or latest_act.get('verticalOscillation')
        vr = s_dto.get('verticalRatio') or latest_act.get('verticalRatio')
        gct = s_dto.get('groundContactTime') or latest_act.get('groundContactTime')
        dyn_parts = []
        if stride:
            s_val = stride / 100 if stride > 20 else stride
            dyn_parts.append(f"步幅 {s_val:.2f}m")
        if vo:
            vo_val = vo / 10 if vo > 20 else vo
            dyn_parts.append(f"垂直振幅 {vo_val:.1f}cm")
        if vr:
            dyn_parts.append(f"步幅比 {vr:.1f}%")
        if gct:
            dyn_parts.append(f"觸地時間 {int(gct)}ms")
        if dyn_parts:
            entry += f"\n動態: {' | '.join(dyn_parts)}"

        # 海拔數據
        gain_el = s_dto.get('elevationGain') or latest_act.get('elevationGain') or 0
        loss_el = s_dto.get('elevationLoss') or latest_act.get('elevationLoss') or 0
        entry += f"\n海拔: 總上升 {int(gain_el)}m | 總下降 {int(loss_el)}m"
        
        # 訓練效果與負荷
        te_aerobic = latest_act.get('aerobicTrainingEffect', 0)
        te_anaerobic = latest_act.get('anaerobicTrainingEffect', 0)
        te_label = s_dto.get('trainingEffectLabel') or latest_act.get('trainingEffectLabel')
        act_load = s_dto.get('activityTrainingLoad') or latest_act.get('activityTrainingLoad')
        vo2_val = s_dto.get('vO2MaxValue') or latest_act.get('vO2MaxValue')
        
        te_str = f"\nTE: 有氧 {te_aerobic:.1f} / 無氧 {te_anaerobic:.1f}"
        if te_label:
            te_str += f" | 主效益: {te_label}"
        if act_load:
            te_str += f" | 負荷: {int(act_load)}"
        if vo2_val:
            te_str += f" | VO2Max: {int(vo2_val)}"
        entry += te_str

        # 心率區間分佈 (HR in Zones)
        hr_zones = fetch_activity_hr_zones(client_garmin, a_id)
        hz_str = format_hr_zones(hr_zones)
        if hz_str:
            entry += f"\n心率區間: {hz_str}"

        # 氣象數據 (Open-Meteo)
        start_lat = s_dto.get('startLatitude') or latest_act.get('startLatitude')
        start_lon = s_dto.get('startLongitude') or latest_act.get('startLongitude')
        start_time = latest_act.get('startTimeLocal') or ''
        
        is_indoor = (start_lat is None or start_lon is None)
        query_lat = DEFAULT_LAT if is_indoor else start_lat
        query_lon = DEFAULT_LON if is_indoor else start_lon

        om_weather_str = "無數據"
        om = get_open_meteo_weather(query_lat, query_lon, start_time)
        if om:
            om_parts = []
            if om.get("temperature") is not None:
                om_parts.append(f"氣溫 {om['temperature']}°C")
            if om.get("humidity") is not None:
                om_parts.append(f"濕度 {om['humidity']}%")
            if om.get("apparent_temperature") is not None:
                om_parts.append(f"體感 {om['apparent_temperature']}°C")
            if om.get("wind_speed") is not None:
                om_parts.append(f"風速 {om['wind_speed']}km/h")
            if om.get("weather_desc"):
                om_parts.append(f"({om['weather_desc']})")
            if om_parts:
                om_weather_str = " | ".join(om_parts)
                if is_indoor:
                    om_weather_str += " (室外測站備援)"

        entry += f"\n🌤️ 環境氣象: {om_weather_str}"

        if other_yesterday_acts:
            other_summaries = "; ".join(format_activity_summary(a) for a in other_yesterday_acts)
            entry += f"\n➕ 昨日其他紀錄: {other_summaries}"
    
        # 分圈細節 (純文字排版) 與 前後半程有氧解耦率
        laps = fetch_activity_splits(client_garmin, a_id)
        decoupling_data = None
        if laps:
            laps_str = format_laps_table(laps)
            entry += f"\n{laps_str}"

            # 計算有氧解耦率 (Decoupling %)
            decoupling_data = calculate_aerobic_decoupling(laps)
            if decoupling_data:
                decoupling_str = format_aerobic_decoupling(decoupling_data)
                entry += f"\n{decoupling_str}"
                print(f"💓 有氧解耦率計算完成: {decoupling_data['decoupling_pct']}% ({decoupling_data['status_desc']})")
        
        report.append(entry)
        report.append("=" * 30)

        full_text = "\n".join(report)

        # 6. 諮詢 AI 教練
        print("🤖 正在諮詢 Gemini AI 教練...")
        ai_advice, used_model = generate_coach_advice(ai_client, candidate_models, full_text)
        
        # 若實際使用模型發生降級，同步更新報表抬頭
        if used_model != best_model:
            full_text = full_text.replace(active_title_tpl.format(model=best_model), active_title_tpl.format(model=used_model))
        
        # 7. 組裝並過濾 LaTeX 語法後推播
        final_message = clean_ai_text(
            full_text + _format_ai_section("🤖 【Gemini AI 教練建議】", ai_advice, used_model, best_model)
        )
        
        send_telegram(final_message)

        # 8. 生成並推播視覺化遙測圖表 (各圖表獨立分開，大字體高清晰)
        print("📊 正在產出專業運動遙測獨立圖表...")
        charts = generate_all_telemetry_charts(
            latest_act,
            laps,
            acwr_data,
            hr_zones,
            decoupling_data=decoupling_data,
            output_dir=LOCAL_SAVE_DIR,
            date_label=f"昨日 {yesterday_date.isoformat()}",
        )
        for c_path, c_caption in charts:
            send_telegram_photo(c_path, caption=c_caption)
            time.sleep(0.5)

        print(f"✅ 任務完成：{get_local_now()}")

    except Exception as e:
        print(f"❌ 腳本執行錯誤: {str(e)}")
        send_telegram(f"❌ Garmin 報表執行錯誤: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run_main_task()
