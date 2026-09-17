import os
import matplotlib
matplotlib.use('Agg')  # 無介面背景渲染，專為伺服器與 CI/CD 設計
import matplotlib.pyplot as plt
import numpy as np

# 設定通用無襯線字型，確保在 Linux/Ubuntu (GitHub Actions) 與 Windows 上皆不缺字
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

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
