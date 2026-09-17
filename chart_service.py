import os
import matplotlib
matplotlib.use('Agg')  # 無介面背景渲染，專為伺服器與 CI/CD 設計
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

# 設定通用無襯線字型，確保在 Linux/Ubuntu (GitHub Actions) 與 Windows 上皆不缺字
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# 全域主題配色 (Dark High-Tech Sporty Theme)
BG_DARK = '#11161f'
PANEL_BG = '#18202c'
CARD_BG = '#0d1219'
TEXT_COLOR = '#e0e6ed'
MUTED_TEXT = '#94a3b8'
GRID_COLOR = '#253245'
CYAN_ACCENT = '#00b4d8'
GREEN_ACCENT = '#00e676'
ORANGE_ACCENT = '#ff9100'
RED_ACCENT = '#ff5252'
PURPLE_ACCENT = '#b388ff'

ZONE_COLORS = ['#81c784', '#64b5f6', '#ffd54f', '#ffb74d', '#e57373']
ZONE_NAMES = ['Z1 Recovery', 'Z2 Aerobic', 'Z3 Tempo', 'Z4 Threshold', 'Z5 Anaerobic']


def generate_acwr_chart(acwr_data, save_path="acwr_chart.png"):
    """繪製獨立 ACWR 負荷比與體能監控圖 (寬敞獨立版面，字體大、清晰易讀)"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        acwr_val = acwr_data.get('acwr', 1.0) if acwr_data else 1.0
        acute = acwr_data.get('acute_load', 0) if acwr_data else 0
        chronic = acwr_data.get('chronic_load', 0) if acwr_data else 0
        status_zone = acwr_data.get('status_zone', 'optimal') if acwr_data else 'optimal'

        zone_name_map = {
            "optimal": "SWEET SPOT (0.8 - 1.3)",
            "caution": "CAUTION (1.3 - 1.5)",
            "danger": "DANGER ZONE (>= 1.5)",
            "under": "RECOVERY / LOW (< 0.8)",
            "building": "BUILDING BASE",
            "rest": "REST PERIOD"
        }
        zone_label = zone_name_map.get(status_zone, "SWEET SPOT")

        # 狀態卡片顏色
        if acwr_val < 0.8:
            status_color = CYAN_ACCENT
        elif acwr_val <= 1.3:
            status_color = GREEN_ACCENT
        elif acwr_val < 1.5:
            status_color = ORANGE_ACCENT
        else:
            status_color = RED_ACCENT

        fig = plt.figure(figsize=(9, 5.2), facecolor=BG_DARK)
        fig.suptitle('ACUTE:CHRONIC WORKLOAD RATIO (ACWR)', 
                     fontsize=15, fontweight='bold', color=TEXT_COLOR, y=0.96)

        # 2 欄網格：左側柱狀圖，右側 ACWR 狀態與科學量規
        gs = fig.add_gridspec(1, 2, width_ratios=[1.1, 1], wspace=0.32, top=0.85, bottom=0.15)

        # --- 左側：7日急性 vs 28日慢性負荷柱狀圖 ---
        ax_bars = fig.add_subplot(gs[0, 0], facecolor=PANEL_BG)
        categories = ['Acute Load\n(Recent 7d)', 'Chronic Load\n(28d Weekly Avg)']
        loads = [acute, chronic]
        bars = ax_bars.bar(categories, loads, color=[CYAN_ACCENT, PURPLE_ACCENT], width=0.45, zorder=3)

        max_load = max(loads) if max(loads) > 0 else 100
        for b in bars:
            h = b.get_height()
            ax_bars.text(b.get_x() + b.get_width()/2., h + max_load*0.03,
                         f'{int(h)}', ha='center', va='bottom', color=TEXT_COLOR, fontweight='bold', fontsize=13)

        ax_bars.set_ylabel('Training Load Value', color=TEXT_COLOR, fontsize=11, fontweight='bold')
        ax_bars.tick_params(axis='x', colors=TEXT_COLOR, labelsize=10)
        ax_bars.tick_params(axis='y', colors=TEXT_COLOR, labelsize=10)
        ax_bars.grid(axis='y', color=GRID_COLOR, linestyle='--', alpha=0.7, zorder=0)
        ax_bars.set_ylim(0, max_load * 1.25)
        for spine in ax_bars.spines.values():
            spine.set_color(GRID_COLOR)

        # --- 右側：ACWR 狀態指針與科學參考量表 ---
        ax_gauge = fig.add_subplot(gs[0, 1], facecolor=PANEL_BG)
        ax_gauge.set_xlim(0, 1)
        ax_gauge.set_ylim(0, 1)
        ax_gauge.axis('off')

        # 頂部大狀態 Badge
        card_text = f"ACWR: {acwr_val:.2f}\n{zone_label}"
        ax_gauge.text(0.5, 0.82, card_text, ha='center', va='center', fontsize=13, fontweight='bold',
                      color=status_color,
                      bbox=dict(boxstyle='round,pad=0.6', facecolor=CARD_BG, edgecolor=status_color, lw=2))

        # 區間刻度條與指標說明
        zones = [
            ("Under (< 0.8)", 0.58, CYAN_ACCENT, "Fitness Decay / Low Load"),
            ("Sweet Spot (0.8 - 1.3)", 0.44, GREEN_ACCENT, "Optimal / Low Injury Risk"),
            ("Caution (1.3 - 1.5)", 0.30, ORANGE_ACCENT, "High Fatigue Accumulation"),
            ("Danger (>= 1.5)", 0.16, RED_ACCENT, "High Injury Danger Zone"),
        ]

        for name, y_pos, color, desc in zones:
            is_current = False
            if name.startswith("Under") and acwr_val < 0.8:
                is_current = True
            elif name.startswith("Sweet") and 0.8 <= acwr_val <= 1.3:
                is_current = True
            elif name.startswith("Caution") and 1.3 < acwr_val < 1.5:
                is_current = True
            elif name.startswith("Danger") and acwr_val >= 1.5:
                is_current = True

            prefix = "▶ " if is_current else "  "
            weight = "bold" if is_current else "normal"

            ax_gauge.text(0.05, y_pos, f"{prefix}{name}", color=color, fontsize=11, fontweight=weight, va='center')
            ax_gauge.text(0.05, y_pos - 0.055, f"   {desc}", color=MUTED_TEXT, fontsize=8.5, va='center')

        plt.savefig(save_path, dpi=160, facecolor=BG_DARK, bbox_inches='tight')
        plt.close(fig)
        return True
    except Exception as e:
        print(f"⚠️ ACWR 圖表生成失敗: {e}")
        try:
            plt.close('all')
        except Exception:
            pass
        return False


def generate_hr_zones_chart(hr_zones_raw, save_path="hr_zones_chart.png"):
    """繪製獨立心率區間分佈環圈圖 (Donut Chart & Breakdown Table)"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        zone_secs = [0, 0, 0, 0, 0]

        if hr_zones_raw:
            items = hr_zones_raw if isinstance(hr_zones_raw, list) else hr_zones_raw.get('values', [])
            for item in items:
                z = item.get('zoneNumber', item.get('zone'))
                sec = item.get('secsInZone', item.get('timeInZone', 0))
                if z and 1 <= int(z) <= 5:
                    zone_secs[int(z) - 1] = sec

        total_sec = sum(zone_secs)

        fig = plt.figure(figsize=(9, 5.2), facecolor=BG_DARK)
        fig.suptitle('HEART RATE ZONES (Z1 - Z5)', 
                     fontsize=15, fontweight='bold', color=TEXT_COLOR, y=0.96)

        if total_sec == 0:
            ax = fig.add_subplot(1, 1, 1, facecolor=PANEL_BG)
            ax.text(0.5, 0.5, 'No Heart Rate Zone Data Logged', ha='center', va='center',
                    color=MUTED_TEXT, fontsize=14, fontweight='bold')
            ax.axis('off')
            plt.savefig(save_path, dpi=160, facecolor=BG_DARK, bbox_inches='tight')
            plt.close(fig)
            return True

        gs = fig.add_gridspec(1, 2, width_ratios=[1.1, 1], wspace=0.15, top=0.85, bottom=0.12)

        # --- 左側：甜甜圈環圈圖 ---
        ax_pie = fig.add_subplot(gs[0, 0], facecolor=BG_DARK)
        
        valid_indices = [i for i, s in enumerate(zone_secs) if s > 0]
        plot_secs = [zone_secs[i] for i in valid_indices]
        plot_colors = [ZONE_COLORS[i] for i in valid_indices]

        wedges, _ = ax_pie.pie(
            plot_secs,
            colors=plot_colors,
            startangle=90,
            wedgeprops=dict(width=0.42, edgecolor=BG_DARK, linewidth=3)
        )

        # 中心文字：總運動時間
        tot_min = int(total_sec // 60)
        tot_sec_rem = int(total_sec % 60)
        time_str = f"{tot_min}:{tot_sec_rem:02d}" if tot_min < 60 else f"{tot_min//60}h {tot_min%60}m"
        ax_pie.text(0, 0.1, "TOTAL TIME", ha='center', va='center', color=MUTED_TEXT, fontsize=9, fontweight='bold')
        ax_pie.text(0, -0.12, time_str, ha='center', va='center', color=TEXT_COLOR, fontsize=16, fontweight='bold')

        # --- 右側：區間細節清單卡片 ---
        ax_list = fig.add_subplot(gs[0, 1], facecolor=PANEL_BG)
        ax_list.set_xlim(0, 1)
        ax_list.set_ylim(0, 1)
        ax_list.axis('off')

        ax_list.text(0.08, 0.90, "ZONE BREAKDOWN", color=TEXT_COLOR, fontsize=12, fontweight='bold')

        y_starts = [0.73, 0.57, 0.41, 0.25, 0.09]
        for i in range(5):
            s = zone_secs[i]
            pct = (s / total_sec * 100) if total_sec > 0 else 0
            m = int(s // 60)
            sec_r = int(s % 60)
            dur_str = f"{m:02d}:{sec_r:02d}"

            y = y_starts[i]
            # 圓點標記
            ax_list.scatter(0.1, y, color=ZONE_COLORS[i], s=100, zorder=3)
            # 區間名稱
            ax_list.text(0.18, y, ZONE_NAMES[i], color=TEXT_COLOR, fontsize=11, fontweight='bold', va='center')
            # 耗時與佔比
            ax_list.text(0.92, y, f"{dur_str} ({pct:4.1f}%)", color=ZONE_COLORS[i] if pct > 0 else MUTED_TEXT,
                         fontsize=11, fontweight='bold', ha='right', va='center')

        plt.savefig(save_path, dpi=160, facecolor=BG_DARK, bbox_inches='tight')
        plt.close(fig)
        return True
    except Exception as e:
        print(f"⚠️ 心率區間圖表生成失敗: {e}")
        try:
            plt.close('all')
        except Exception:
            pass
        return False


def generate_laps_trend_chart(laps, save_path="laps_trend_chart.png"):
    """繪製獨立分圈配速與心率走勢圖 (Dual-axis Lap Pace & HR Trend，配速 M:SS 軸格式化)"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        fig = plt.figure(figsize=(10, 5.5), facecolor=BG_DARK)
        fig.suptitle('LAP-BY-LAP PACE & HEART RATE TREND', 
                     fontsize=15, fontweight='bold', color=TEXT_COLOR, y=0.96)

        if not laps or len(laps) <= 1:
            ax = fig.add_subplot(1, 1, 1, facecolor=PANEL_BG)
            ax.text(0.5, 0.5, 'Single Lap / Rest Day (No Multi-lap Trend)', ha='center', va='center',
                    color=MUTED_TEXT, fontsize=14, fontweight='bold')
            ax.axis('off')
            plt.savefig(save_path, dpi=160, facecolor=BG_DARK, bbox_inches='tight')
            plt.close(fig)
            return True

        ax_pace = fig.add_subplot(1, 1, 1, facecolor=PANEL_BG)
        lap_nums = [i + 1 for i in range(len(laps))]
        paces = []
        hrs = []
        for l in laps:
            spd = l.get('averageSpeed', 0)
            p_min = (1000 / spd) / 60 if spd > 0 else 6.0
            paces.append(p_min)
            hrs.append(l.get('averageHR', 0))

        # --- 繪製配速 (左 Y 軸，反轉使配速越快在上方) ---
        line_pace = ax_pace.plot(lap_nums, paces, color=CYAN_ACCENT, marker='o', markersize=6,
                                 lw=2.5, label='Pace (min/km)', zorder=3)
        ax_pace.set_ylabel('Pace (min/km)', color=CYAN_ACCENT, fontsize=11, fontweight='bold')
        ax_pace.tick_params(axis='y', colors=CYAN_ACCENT, labelsize=10)
        ax_pace.invert_yaxis()

        # 配速軸標籤格式化為 M:SS (例如 5.25 轉為 5:15)
        def pace_fmt(val, pos):
            m = int(val)
            s = int(round((val - m) * 60))
            if s >= 60:
                m += 1
                s = 0
            return f"{m}:{s:02d}"
        from matplotlib.ticker import MaxNLocator
        ax_pace.yaxis.set_major_locator(MaxNLocator(nbins=6))
        ax_pace.yaxis.set_major_formatter(FuncFormatter(pace_fmt))

        # --- 繪製心率 (右 Y 軸，強制整數刻度) ---
        ax_hr = ax_pace.twinx()
        line_hr = ax_hr.plot(lap_nums, hrs, color=RED_ACCENT, marker='s', markersize=6,
                             lw=2.5, linestyle='--', label='Heart Rate (bpm)', zorder=3)
        ax_hr.set_ylabel('Heart Rate (bpm)', color=RED_ACCENT, fontsize=11, fontweight='bold')
        ax_hr.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
        ax_hr.tick_params(axis='y', colors=RED_ACCENT, labelsize=10)

        # X 軸配置
        ax_pace.set_xlabel('Lap Index (km)', color=TEXT_COLOR, fontsize=11, fontweight='bold')
        ax_pace.set_xticks(lap_nums)
        ax_pace.set_xticklabels([f"L{n}" for n in lap_nums], color=TEXT_COLOR, fontsize=10)
        ax_pace.tick_params(axis='x', colors=TEXT_COLOR)
        ax_pace.grid(True, color=GRID_COLOR, linestyle=':', alpha=0.7)

        # 合併圖例於圖表上方，確保與大標題有充裕安全間隙
        lines = line_pace + line_hr
        labels = [l.get_label() for l in lines]
        ax_pace.legend(lines, labels, loc='lower center', bbox_to_anchor=(0.5, 1.02), ncol=2,
                       fontsize=10, facecolor=CARD_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)

        for spine in ax_pace.spines.values():
            spine.set_color(GRID_COLOR)
        for spine in ax_hr.spines.values():
            spine.set_color(GRID_COLOR)

        plt.subplots_adjust(top=0.81, bottom=0.14, left=0.12, right=0.88)
        plt.savefig(save_path, dpi=160, facecolor=BG_DARK, bbox_inches='tight')
        plt.close(fig)
        return True
    except Exception as e:
        print(f"⚠️ 分圈走勢圖表生成失敗: {e}")
        try:
            plt.close('all')
        except Exception:
            pass
        return False


def generate_all_telemetry_charts(latest_act, laps, acwr_data, hr_zones_raw, output_dir="."):
    """生成所有個別獨立的遙測圖表，回傳 [(檔案路徑, Telegram 圖說 Caption)] 清單。
    每個圖表單獨繪製，字體更大、排版寬敞、在手機 Telegram 瀏覽時清晰無比！
    """
    charts = []

    # 1. ACWR 負荷比與體能監控圖 (運動日與休整日皆產出)
    if acwr_data:
        acwr_file = os.path.join(output_dir, "acwr_chart.png")
        if generate_acwr_chart(acwr_data, acwr_file):
            caption = f"📈 【ACWR 急性與慢性負荷監控】\n比值: {acwr_data.get('acwr', 'N/A')} ({acwr_data.get('status_desc', '')})"
            charts.append((acwr_file, caption))

    # 2. 心率區間分佈圖 (僅在有心率區間數據時產出)
    if hr_zones_raw:
        hr_file = os.path.join(output_dir, "hr_zones_chart.png")
        if generate_hr_zones_chart(hr_zones_raw, hr_file):
            caption = "💓 【心率區間分佈 (Z1 ~ Z5)】\n各心率區間訓練時間與強度佔比"
            charts.append((hr_file, caption))

    # 3. 分圈配速與心率走勢圖 (僅在有 2 圈以上分圈數據時產出)
    if laps and len(laps) > 1:
        laps_file = os.path.join(output_dir, "laps_trend_chart.png")
        if generate_laps_trend_chart(laps, laps_file):
            caption = f"⚡ 【各公里配速與心率走勢】\n共 {len(laps)} 公里分圈穩定度與心率漂移分析"
            charts.append((laps_file, caption))

    return charts


def generate_telemetry_chart(latest_act, laps, acwr_data, hr_zones_raw, save_path):
    """繪製專業運動遙測視覺化儀表板 (Dark High-Tech Sporty Theme)
    含：ACWR 負荷指針、Z1~Z5 心率分佈、分圈配速與心率走勢。
    若繪圖過程發生任何例外，安全捕捉並回傳 False，確保主任務不中斷。
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        
        # 顏色主題設定
        bg_dark = '#11161f'
        panel_bg = '#18202c'
        text_color = '#e0e6ed'
        grid_color = '#253245'
        cyan_accent = '#00b4d8'
        green_accent = '#00e676'
        orange_accent = '#ff9100'
        red_accent = '#ff5252'
        purple_accent = '#b388ff'

        fig = plt.figure(figsize=(12, 6.5), facecolor=bg_dark)
        fig.suptitle('GARMIN AI COACH - TELEMETRY & WORKLOAD DASHBOARD', 
                     fontsize=15, fontweight='bold', color=text_color, y=0.96)

        # 網格配置：左側 ACWR 佔 1 欄，右側分為上下 2 欄
        gs = fig.add_gridspec(2, 2, width_ratios=[1, 1.3], wspace=0.28, hspace=0.38)
        
        # ==========================================
        # Panel 1 (左側跨兩列): ACWR 負荷監控與體能評估
        # ==========================================
        ax_acwr = fig.add_subplot(gs[:, 0], facecolor=panel_bg)
        acwr_val = acwr_data.get('acwr', 1.0) if acwr_data else 1.0
        acute = acwr_data.get('acute_load', 0) if acwr_data else 0
        chronic = acwr_data.get('chronic_load', 0) if acwr_data else 0
        status_zone = acwr_data.get('status_zone', 'optimal') if acwr_data else 'optimal'
        zone_name_map = {
            "optimal": "SWEET SPOT (0.8 - 1.3)",
            "caution": "CAUTION (1.3 - 1.5)",
            "danger": "DANGER ZONE (>= 1.5)",
            "under": "RECOVERY / LOW (< 0.8)",
            "building": "BUILDING BASE",
            "rest": "REST PERIOD"
        }
        zone_label = zone_name_map.get(status_zone, "SWEET SPOT")

        # 柱狀對比 (Acute vs Chronic)
        categories = ['Acute (7d)', 'Chronic (28d/wk)']
        loads = [acute, chronic]
        bar_colors = [cyan_accent, purple_accent]
        
        bars = ax_acwr.bar(categories, loads, color=bar_colors, width=0.48, zorder=3)
        for b in bars:
            h = b.get_height()
            ax_acwr.text(b.get_x() + b.get_width()/2., h + max(loads)*0.02,
                         f'{int(h)}', ha='center', va='bottom', color=text_color, fontweight='bold', fontsize=11)

        # ACWR 狀態卡片文字
        status_color = green_accent
        if acwr_val < 0.8:
            status_color = cyan_accent
        elif acwr_val <= 1.3:
            status_color = green_accent
        elif acwr_val < 1.5:
            status_color = orange_accent
        else:
            status_color = red_accent

        card_text = f"ACWR: {acwr_val:.2f}\n{zone_label}"
        ax_acwr.text(0.5, 0.88, card_text, transform=ax_acwr.transAxes,
                     ha='center', va='center', fontsize=12, fontweight='bold',
                     color=status_color, bbox=dict(boxstyle='round,pad=0.5', facecolor='#0f141c', edgecolor=status_color, lw=1.5))

        ax_acwr.set_title('ACUTE:CHRONIC WORKLOAD RATIO', color=text_color, fontsize=12, fontweight='bold', pad=12)
        ax_acwr.set_ylabel('Training Load', color=text_color, fontsize=10)
        ax_acwr.tick_params(colors=text_color)
        ax_acwr.grid(axis='y', color=grid_color, linestyle='--', alpha=0.7, zorder=0)
        ax_acwr.set_ylim(0, max(loads) * 1.35 if max(loads) > 0 else 100)

        # ==========================================
        # Panel 2 (右上): 心率區間分佈 (Z1 ~ Z5)
        # ==========================================
        ax_zones = fig.add_subplot(gs[0, 1], facecolor=panel_bg)
        zone_labels = ['Z1 Recovery', 'Z2 Aerobic', 'Z3 Tempo', 'Z4 Threshold', 'Z5 Anaerobic']
        zone_colors = ['#81c784', '#64b5f6', '#ffd54f', '#ffb74d', '#e57373']
        zone_secs = [0, 0, 0, 0, 0]

        if hr_zones_raw:
            items = hr_zones_raw if isinstance(hr_zones_raw, list) else hr_zones_raw.get('values', [])
            for item in items:
                z = item.get('zoneNumber', item.get('zone'))
                sec = item.get('secsInZone', item.get('timeInZone', 0))
                if z and 1 <= int(z) <= 5:
                    zone_secs[int(z) - 1] = sec

        total_sec = sum(zone_secs)
        if total_sec > 0:
            left_pos = 0
            for idx in range(5):
                pct = (zone_secs[idx] / total_sec) * 100
                if pct > 0:
                    ax_zones.barh(0, pct, left=left_pos, color=zone_colors[idx], height=0.5, edgecolor=bg_dark, label=f'Z{idx+1} ({pct:.0f}%)')
                    if pct >= 8:
                        ax_zones.text(left_pos + pct/2, 0, f'{pct:.0f}%', ha='center', va='center', color='#111', fontweight='bold', fontsize=9)
                    left_pos += pct
            ax_zones.set_xlim(0, 100)
            ax_zones.set_yticks([])
            ax_zones.set_xlabel('Zone Distribution (%)', color=text_color, fontsize=9)
            ax_zones.legend(loc='lower center', bbox_to_anchor=(0.5, 1.05), ncol=5, fontsize=8,
                            facecolor=panel_bg, edgecolor=grid_color, labelcolor=text_color)
        else:
            ax_zones.text(0.5, 0.5, 'No HR Zones Logged', ha='center', va='center', color='#888', fontsize=11)
            ax_zones.set_xticks([])
            ax_zones.set_yticks([])

        ax_zones.set_title('HEART RATE ZONES (Z1-Z5)', color=text_color, fontsize=11, fontweight='bold', pad=22)
        ax_zones.tick_params(colors=text_color)
        for spine in ax_zones.spines.values():
            spine.set_color(grid_color)

        # ==========================================
        # Panel 3 (右下): 分圈配速與心率走勢
        # ==========================================
        ax_laps = fig.add_subplot(gs[1, 1], facecolor=panel_bg)
        
        if laps and len(laps) > 1:
            lap_nums = [i + 1 for i in range(len(laps))]
            paces = []
            hrs = []
            for l in laps:
                spd = l.get('averageSpeed', 0)
                p_min = (1000 / spd) / 60 if spd > 0 else 6.0
                paces.append(p_min)
                hrs.append(l.get('averageHR', 0))

            # 繪製配速 (左軸)
            line1 = ax_laps.plot(lap_nums, paces, color=cyan_accent, marker='o', lw=2, label='Pace (min/km)')
            ax_laps.set_ylabel('Pace (min/km)', color=cyan_accent, fontsize=9)
            ax_laps.tick_params(axis='y', colors=cyan_accent)
            ax_laps.invert_yaxis()  # 配速越快在上方

            # 繪製心率 (右軸)
            ax_hr = ax_laps.twinx()
            line2 = ax_hr.plot(lap_nums, hrs, color=red_accent, marker='s', lw=2, linestyle='--', label='Heart Rate (bpm)')
            ax_hr.set_ylabel('Heart Rate (bpm)', color=red_accent, fontsize=9)
            ax_hr.tick_params(axis='y', colors=red_accent)

            ax_laps.set_xlabel('Lap Index (km)', color=text_color, fontsize=9)
            ax_laps.set_xticks(lap_nums)
            ax_laps.tick_params(axis='x', colors=text_color)
            ax_laps.grid(True, color=grid_color, linestyle=':', alpha=0.6)
            
            # 合併圖例
            lines = line1 + line2
            labels = [l.get_label() for l in lines]
            ax_laps.legend(lines, labels, loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=2, fontsize=8,
                           facecolor=panel_bg, edgecolor=grid_color, labelcolor=text_color)
        else:
            ax_laps.text(0.5, 0.5, 'Single Lap / Rest Day', ha='center', va='center', color='#888', fontsize=11)
            ax_laps.set_xticks([])
            ax_laps.set_yticks([])

        ax_laps.set_title('LAP PACE & HEART RATE TREND', color=text_color, fontsize=11, fontweight='bold', pad=18)
        for spine in ax_laps.spines.values():
            spine.set_color(grid_color)

        plt.savefig(save_path, dpi=150, facecolor=bg_dark, bbox_inches='tight')
        plt.close(fig)
        return True
    except Exception as e:
        print(f"⚠️ 視覺化圖表生成失敗: {e}")
        try:
            plt.close('all')
        except Exception:
            pass
        return False
