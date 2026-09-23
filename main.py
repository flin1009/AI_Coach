import datetime
import os
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
    format_pace,
    format_duration,
    format_hr_zones,
    clean_ai_text,
    format_activity_summary,
    format_laps_table,
    check_activity_recency,
    calculate_weekly_stats,
    calculate_acwr,
    format_recovery_metrics,
    calculate_vdot_paces,
    format_vdot_paces,
    calculate_aerobic_decoupling,
    format_aerobic_decoupling,
    format_upcoming_races
)
from weather_service import get_open_meteo_weather
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
        extended_activities = fetch_extended_activities(client_garmin, count=35)
        acwr_data = calculate_acwr(extended_activities if extended_activities else activities)
        print(f"📈 ACWR 負荷比計算: {acwr_data['acwr']} ({acwr_data['status_desc']}) | 急性: {acwr_data['acute_load']} | 慢性: {acwr_data['chronic_load']}")

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

        # 4. 取得未來目標賽事 (近三個月/90天)
        upcoming_races = fetch_upcoming_races(client_garmin, months_ahead=3)
        races_str = format_upcoming_races(upcoming_races)
        if races_str:
            print(f"🏆 成功取得近期目標賽事: {len(upcoming_races)} 場")
        else:
            print("ℹ️ 近期三個月內未排定目標賽事。")

        latest_act = activities[0]
        start_time_str = latest_act.get('startTimeLocal', '')
        is_recent, diff_hours = check_activity_recency(start_time_str, max_hours=36)

        # 若最新活動距今超過 36 小時，自動切換為【休整與超補償日報】模式
        if not is_recent:
            print(f"🌿 最新活動距今約 {diff_hours:.1f} 小時 (> 36h)，切換為【今日休整與體能恢復日報】模式...")
            days_ago = int(diff_hours // 24)
            hours_ago = int(diff_hours % 24)
            time_ago_str = f"{days_ago} 天 {hours_ago} 小時前" if days_ago > 0 else f"{hours_ago} 小時前"
            
            stats = calculate_weekly_stats(activities)
            
            report = []
            report.append(f"🌿 【{RUNNER_NAME} 今日休整與體能恢復日報 - {best_model}】")
            report.append(f"背景：{RUNNER_BIRTH_YEAR}年生 | PB {RUNNER_PB} | Zone 2: {ZONE2_MAX_HR}bpm")
            report.append(f"狀態：今日無新運動紀錄 (前次訓練於 {time_ago_str})")
            report.append("=" * 30)

            if vdot_str:
                report.append(vdot_str)
                report.append("-" * 30)

            if races_str:
                report.append(races_str)
                report.append("-" * 30)

            if recovery_str:
                report.append(recovery_str)
                report.append("-" * 30)

            report.append("📈 【ACWR 急性與慢性負荷監控 (近28日)】")
            report.append(f"  - ACWR 比值: {acwr_data['acwr']} ({acwr_data['status_desc']})")
            report.append(f"  - 急性負荷 (近7日): {acwr_data['acute_load']} | 慢性負荷 (28日週均): {acwr_data['chronic_load']}")
            report.append("-" * 30)
            
            report.append(f"📊 【近一週累積運動統計 (近 {stats['total_activities']} 筆)】")
            report.append(f"  - 累積總跑量: {stats['total_run_km']:.2f} km")
            report.append(f"  - 跑步總耗時: {stats['total_run_duration']}")
            report.append(f"  - 累積總負荷: {stats['total_load']}")
            report.append(f"  - 訓練次數: {stats['run_count']} 次跑步 / {stats['cross_count']} 次交叉訓練")
            report.append("-" * 30)
            
            report.append(f"📋 【近期訓練歷程明細】")
            for act in activities:
                summary_line = format_activity_summary(act)
                report.append(f"  - {summary_line}")
            report.append("=" * 30)
            
            full_text = "\n".join(report)
            print("🤖 正在諮詢 Gemini AI 休整與超補償建議...")
            ai_advice, used_model = generate_rest_day_advice(ai_client, candidate_models, full_text)
            
            if used_model != best_model:
                full_text = full_text.replace(f"🌿 【{RUNNER_NAME} 今日休整與體能恢復日報 - {best_model}】", f"🌿 【{RUNNER_NAME} 今日休整與體能恢復日報 - {used_model}】")
            
            final_message = full_text + "\n\n🤖 【Gemini 休整與超補償指引】\n" + clean_ai_text(ai_advice)
            final_message = clean_ai_text(final_message)
            
            send_telegram(final_message)

            # 生成並推播休整圖表 (各圖表獨立分開，大字體高清晰)
            print("📊 正在產出休整與 ACWR 負荷圖表...")
            charts = generate_all_telemetry_charts(None, None, acwr_data, None, output_dir=LOCAL_SAVE_DIR)
            for c_path, c_caption in charts:
                send_telegram_photo(c_path, caption=c_caption)
                time.sleep(0.5)

            print(f"✅ 今日休整任務完成：{datetime.datetime.now()}")
            return

        # 4. 組裝報表抬頭 (最新活動模式)
        report = []
        report.append(f"📊 【{RUNNER_NAME} 數據分析報表 - {best_model}】")
        report.append(f"背景：{RUNNER_BIRTH_YEAR}年生 | PB {RUNNER_PB} | Zone 2: {ZONE2_MAX_HR}bpm")
        report.append("=" * 30)

        if vdot_str:
            report.append(vdot_str)
            report.append("-" * 30)

        if races_str:
            report.append(races_str)
            report.append("-" * 30)

        if recovery_str:
            report.append(recovery_str)
            report.append("-" * 30)

        report.append("📈 【ACWR 急性與慢性負荷監控 (近28日)】")
        report.append(f"  - ACWR 比值: {acwr_data['acwr']} ({acwr_data['status_desc']})")
        report.append(f"  - 急性負荷 (近7日): {acwr_data['acute_load']} | 慢性負荷 (28日週均): {acwr_data['chronic_load']}")
        report.append("-" * 30)

        # 5. 近期訓練脈絡 (近 7 筆歷程簡要列表)
        report.append(f"📋 【近期訓練歷程 (近 {len(activities)} 筆摘要)】")
        for idx, act in enumerate(activities):
            tag = " [最新]" if idx == 0 else ""
            summary_line = format_activity_summary(act)
            report.append(f"  - {summary_line}{tag}")
        report.append("-" * 30)

        # 5. 最新活動深度解剖 (僅針對 activities[0])
        latest_act = activities[0]
        a_id = latest_act["activityId"]
        s_dto = latest_act.get('summaryDTO', {})
        
        entry = f"🏃 【最新活動深度數據】"
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
            if om.get("weather_desc"):
                om_parts.append(f"({om['weather_desc']})")
            if om_parts:
                om_weather_str = " | ".join(om_parts)
                if is_indoor:
                    om_weather_str += " (室外測站備援)"

        entry += f"\n🌤️ 環境氣象: {om_weather_str}"
    
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
            full_text = full_text.replace(f"📊 【{RUNNER_NAME} 數據分析報表 - {best_model}】", f"📊 【{RUNNER_NAME} 數據分析報表 - {used_model}】")
        
        # 7. 組裝並過濾 LaTeX 語法後推播
        final_message = full_text + "\n\n🤖 【Gemini AI 教練建議】\n" + clean_ai_text(ai_advice)
        final_message = clean_ai_text(final_message)
        
        send_telegram(final_message)

        # 8. 生成並推播視覺化遙測圖表 (各圖表獨立分開，大字體高清晰)
        print("📊 正在產出專業運動遙測獨立圖表...")
        charts = generate_all_telemetry_charts(latest_act, laps, acwr_data, hr_zones, decoupling_data=decoupling_data, output_dir=LOCAL_SAVE_DIR)
        for c_path, c_caption in charts:
            send_telegram_photo(c_path, caption=c_caption)
            time.sleep(0.5)

        print(f"✅ 任務完成：{datetime.datetime.now()}")

    except Exception as e:
        print(f"❌ 腳本執行錯誤: {str(e)}")
        send_telegram(f"❌ Garmin 報表執行錯誤: {str(e)}")

if __name__ == "__main__":
    run_main_task()
