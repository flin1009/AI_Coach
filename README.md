# 🏃 AI Coach - 個人化智慧馬拉松 AI 教練

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated-green.svg)](https://github.com/features/actions)
[![Garmin Connect](https://img.shields.io/badge/Garmin-Connect_API-007cc3.svg)](https://connect.garmin.com/)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-Flash_AI-orange.svg)](https://ai.google.dev/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot_Push-24A1DE.svg)](https://telegram.org/)

**AI Coach** 是一個專為耐力跑者打造的「全自動化智慧訓練診斷系統」。系統每日透過 **GitHub Actions** 定時排程自動執行，主動調閱 **Garmin Connect** 最新跑步與交叉訓練數據，整合 **Open-Meteo** 活動當下之精準歷史溫濕度氣象，並透過 **Google Gemini AI**（具備多模型自動降級備援技術）進行「7 筆微週期訓練負荷評估」與「最新課表全維度深層解剖」，最終將結構化的診斷報告與個人化訓練建議直接推播至跑者的 **Telegram**。

---

## 📐 系統架構圖 (System Architecture)

<div align="center">
  <img src="assets/architecture.png" alt="AI Coach System Architecture" width="100%" style="border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);" />
</div>

<br/>

<details open>
<summary><b>📊 點擊切換 / 展開 互動式向量流程圖 (Mermaid High-Contrast Diagram)</b></summary>

```mermaid
flowchart TB
    %% ================= 階段一：觸發、調度與資料採集 =================
    subgraph STAGE1["<b>【第一階段】自動排程、流程協調調度與數據採集</b>"]
        direction LR
        subgraph G_TRIG["⏰ 觸發與快取 (Trigger)"]
            direction TB
            GHA["<b>GitHub Actions</b><br/>每日定時排程 (Cron)<br/>網頁按鈕手動觸發"]
            CACHE["<b>actions/cache @ v4</b><br/>Garmin Token 跨日雲端快取"]
        end

        subgraph G_CORE["⚙️ 核心調度中心 (Orchestrator)"]
            direction TB
            MAIN["<b>main.py</b><br/>主流程調度引擎<br/>36h 課表/休整日判定"]
            CONF["<b>config.py</b><br/>Secrets & 跑者設定"]
            UTIL["<b>utils.py</b><br/>ACWR / 配速換算 / 數據運算"]
        end

        subgraph G_DATA["📡 數據採集層 (Data Services)"]
            direction TB
            GARMIN["<b>garmin_service.py</b><br/>OAuth 免密登入 / 帳密回退<br/>活動歷程、分圈、HRV、RHR"]
            WEATHER["<b>weather_service.py</b><br/>Open-Meteo 氣象 API<br/>GPS 座標活動當下精準溫濕度"]
        end
    end

    %% ================= 階段二：AI 推理、圖表與推播 =================
    subgraph STAGE2["<b>【第二階段】AI 智慧診斷、3大獨立高清圖表與 Telegram 推播</b>"]
        direction LR
        subgraph G_AI["🧠 智慧推理層 (AI Coach)"]
            direction TB
            AI["<b>ai_service.py</b><br/>Gemini 2.5 / 2.0 Flash 備援<br/>自適應課表辨識<br/>7日微週期累積疲勞診斷"]
        end

        subgraph G_CHART["📊 專業遙測視覺化 (Charts)"]
            direction TB
            CHART["<b>chart_service.py</b><br/>Matplotlib 深色高科技風格<br/>3 張獨立高清大圖：<br/>• 📈 ACWR 負荷比量規圖<br/>• 💓 Z1~Z5 心率區間甜甜圈<br/>• ⚡ 各公里配速心率雙軸走勢"]
        end

        subgraph G_PUSH["📲 雙軌推播層 (Notification)"]
            direction TB
            NOTIFY["<b>notifier.py</b><br/>HTML 等寬分圈表格容錯推播<br/>sendPhoto 高清圖片逐張發送"]
            TG[("<b>Telegram 跑者手機</b><br/>💬 結構化深度日報<br/>🖼️ 3 張滿版大圖無壓縮呈現")]
        end
    end

    %% 外部雲端節點
    GARMIN_CLOUD[("⌚ Garmin Connect 雲端")]
    METEO_CLOUD[("🌤️ Open-Meteo 雲端測站")]
    GEMINI_CLOUD[("✨ Google Gemini AI 雲端")]

    %% 連線關聯
    GHA -->|1. 啟動環境| MAIN
    CACHE <-->|還原 / 更新 Token| GARMIN
    CONF -.->|注入參數| MAIN
    UTIL -.->|輔助計算| MAIN

    MAIN -->|2. 調閱近28天歷程與生理| GARMIN
    GARMIN <-->|API 查詢| GARMIN_CLOUD

    MAIN -->|3. GPS座標與時間查詢| WEATHER
    WEATHER <-->|歷史天候| METEO_CLOUD

    MAIN -->|4. 彙整全維度數據| AI
    AI <-->|多模型容錯調用| GEMINI_CLOUD

    MAIN -->|5. 產出 3 張獨立大圖| CHART
    STAGE1 ==>|完成數據採集| STAGE2

    CHART -->|傳遞圖檔清單| NOTIFY
    AI -->|傳遞教練診斷| NOTIFY
    NOTIFY -->|6. 逐項推播手機| TG

    %% 高對比、大字體樣式定義 (深色高對比底色 + 純白粗體字，保證在 GitHub 淺色/深色模式下皆極度清晰)
    classDef triggerNode fill:#1e1b4b,stroke:#818cf8,stroke-width:2.5px,color:#ffffff;
    classDef coreNode fill:#0f172a,stroke:#38bdf8,stroke-width:2.5px,color:#ffffff;
    classDef dataNode fill:#064e3b,stroke:#34d399,stroke-width:2.5px,color:#ffffff;
    classDef aiNode fill:#3b0764,stroke:#c084fc,stroke-width:2.5px,color:#ffffff;
    classDef chartNode fill:#431407,stroke:#fb923c,stroke-width:2.5px,color:#ffffff;
    classDef pushNode fill:#083344,stroke:#22d3ee,stroke-width:2.5px,color:#ffffff;
    classDef cloudNode fill:#1e293b,stroke:#94a3b8,stroke-width:2px,color:#ffffff;

    class GHA,CACHE triggerNode;
    class MAIN,CONF,UTIL coreNode;
    class GARMIN,WEATHER dataNode;
    class AI aiNode;
    class CHART chartNode;
    class NOTIFY,TG pushNode;
    class GARMIN_CLOUD,METEO_CLOUD,GEMINI_CLOUD cloudNode;

    style STAGE1 fill:#0f141c,stroke:#334155,stroke-width:2px,color:#38bdf8
    style STAGE2 fill:#0f141c,stroke:#334155,stroke-width:2px,color:#38bdf8
    style G_TRIG fill:#161f2e,stroke:#475569,stroke-width:1px,color:#e2e8f0
    style G_CORE fill:#161f2e,stroke:#475569,stroke-width:1px,color:#e2e8f0
    style G_DATA fill:#161f2e,stroke:#475569,stroke-width:1px,color:#e2e8f0
    style G_AI fill:#161f2e,stroke:#475569,stroke-width:1px,color:#e2e8f0
    style G_CHART fill:#161f2e,stroke:#475569,stroke-width:1px,color:#e2e8f0
    style G_PUSH fill:#161f2e,stroke:#475569,stroke-width:1px,color:#e2e8f0
```
</details>

---

## 🌟 核心功能亮點

### 1. ⌚ 全維度 Garmin 數據深度解剖
* **基礎運動表現**：移動與總耗時對比、距離、卡路里、平均/最佳配速、平均/最高心率。
* **高階跑步動態 (Running Dynamics)**：全面解析 **跑步功率 (W)**、**步頻 (spm)**、**步幅 (m)**、**垂直振幅 (cm)**、**步幅比 (%)** 與 **觸地時間 (ms)**，診斷跑姿經濟性與著地負擔。
* **心率區間分佈 (Z1~Z5)**：自動換算各區間累計時間與佔比，檢視能量系統刺激比例。
* **生理負荷評估**：有氧/無氧訓練效果 (Training Effect, TE)、活動訓練負荷值 (Activity Training Load) 與 VO2 Max。
* **詳細分圈明細**：逐公里記錄配速、心率、步頻、爬升高度。

### 2. 🌤️ 歷史氣候精準還原 (Open-Meteo)
* 系統根據活動的 **起始經緯度座標** 與 **起跑時間**，動態查詢 Open-Meteo 每小時歷史氣象數據。
* 即時帶出當時氣溫、相對濕度、體感溫度與天氣概況，幫助 AI 評估熱壓力、補水效率與心率漂移（Cardiac Drift）。
* 若為室內跑步（無 GPS 軌跡），系統自動切換至預設測站座標查詢室外天候。

### 3. 🤖 自適應課表判讀與 Gemini 503 備援機制
* **自適應課表類型辨識**：不拘泥於單一 Zone 2 判斷，AI 自動依心率、配速、功率與各區間佔比，精準識別：
  * 🟢 輕鬆恢復跑 (Recovery Run)
  * 🔵 有氧基礎耐力跑 (Zone 2 Endurance)
  * 🟡 馬拉松配速跑 (Marathon Pace, MP)
  * 🟠 乳酸閾值 / 節奏跑 (Tempo Run)
  * 🔴 高強度間歇 / 衝刺 (Interval)
* **7 筆微週期疲勞監控**：前 6 筆活動提供一週累積總跑量、交叉訓練（自行車、重訓、游泳等）脈絡，診斷急性疲勞指數（Acute Training Load），給予次日最科學的訓練/休整處方。
* **動態多模型降級 (Fallback Mechanism)**：啟動時自動掃描 Google 最新版 Flash 模型清單並由新至舊排序。遭遇 Google 伺服器尖峰 503 UNAVAILABLE 錯誤時，自動無縫切換備援模型重試。

### 4. 📈 ACWR 負荷比與體能監測 (Acute:Chronic Workload Ratio)
* 自動回溯近 28 天訓練大數據，精準計算急劇負荷（近 7 天）與慢性體能（近 28 天週均）之比值。
* 科學標記體能增長區間與預防受傷風險：
  * 🟢 **最佳適應甜點區 (Sweet Spot, 0.8 ~ 1.3)**：安全增長有氧體能，受傷風險最低。
  * 🟡 **疲勞警戒期 (Caution, 1.3 ~ 1.5)**：急劇疲勞快速累積，提醒跑者密切監控肌肉狀態。
  * 🔴 **高受傷風險區 (Danger Zone, ≥ 1.5)**：過度訓練預警，AI 教練主動介入要求減量。

### 5. 🩺 智慧生理指標優雅降級 (Graceful Degradation)
* 自動安全讀取夜間 **HRV 心率變異度**（前夜平均、7日基準線、平衡狀態）、**靜止心率 (RHR)** 與 **身體電量**。
* **零干擾防護**：若手錶未同步或未配戴入睡，系統自動無縫略過該區塊，絕不拋錯中斷；有數據時無縫融入 AI 提示詞評估中樞神經系統修復度。

### 6. 📊 專業遙測圖表與 Telegram 智慧推播
* **獨立高清晰度圖表 (Standalone Telemetry Charts)**：告別多圖擠在一起排版擁擠的困擾，系統將各項核心指標獨立繪製為大尺寸圖表（包含 **ACWR 急性與慢性負荷指標圖**、**Z1~Z5 心率區間環圈甜甜圈圖**、**各公里配速心率雙軸走勢圖**），透過 Telegram 逐張推播，手機端滿版呈現、字體大且數據清晰易讀。
* **分圈等寬表格 (Monospace)**：逐公里數據以 `<pre>` 標籤排版，在手機端呈現整齊不折行的專業表格。
* **LaTeX 符號淨化**：自動過濾 AI 產生的 `$\rightarrow$` 數學符號為標準箭頭 `→`。

### 7. 🔑 Garmin OAuth Token 快取與 GitHub Actions 跨排程持久化
* **防限流與秒速連線**：優先讀取本地已保存之 OAuth Token（預設 `~/.garminconnect`，亦支援 `GARMINTOKENS` 自訂路徑）直接恢復連線，免去重複執行帳密 SSO 驗證流程，大幅降低觸發 Garmin 伺服器 Cloudflare 防爬蟲或 429 Too Many Requests 阻擋之風險。
* **智慧安全回退**：若無快取或 Token 過期，自動退回使用帳號密碼登入，並重新快取新 Token。
* **GitHub Actions 雲端持久化**：工作流程整合 `actions/cache@v4`，每次排程執行完畢自動將 Token 快取至 GitHub 雲端，隔日自動還原使用。
* **資安防護**：`.gitignore` 預設排除 `.garminconnect/` 與 Token 相關 JSON 檔案，防止個人憑證外洩。

---

## 📂 專案檔案結構 (File Structure)

```text
AI_Coach/
├── .github/
│   └── workflows/
│       └── daily_task.yml       # GitHub Actions 每日排程、actions/cache Token 雲端快取與環境依賴
├── config.py                    # 集中管理 Secrets 環境變數與跑者個人化參數
├── utils.py                     # 配速換算、ACWR 計算、心率統計、分圈表格與文字淨化工具
├── weather_service.py           # Open-Meteo 氣象 API 連線與數據擷取模組
├── chart_service.py             # 專業運動遙測儀表板圖表繪製模組 (Matplotlib 深色風格)
├── notifier.py                  # Telegram 機器人文字訊息與圖表圖片推播
├── garmin_service.py            # Garmin Connect 登入驗證 (Token 本地快取)、活動、生理恢復解析
├── ai_service.py                # Gemini AI 模型動態掃描、503 降級備援與教練 Prompt 封裝
├── main.py                      # 系統主調度核心（GitHub Actions 執行入口點）
├── .gitignore                   # Git 排除清單（忽略 Token 憑證、快取、虛擬環境與本機記錄）
└── README.md                    # 專案詳細介紹與架構文檔
```

---

## 🔑 依賴 API 清單與申請教學 (APIs & Prerequisites)

本專案運作需串接以下 4 項服務，各服務的申請需求與教學如下：

| 服務名稱 | 角色與用途 | 是否需申請 | 費用 | 取得方式 / 參考教學 |
| :--- | :--- | :---: | :---: | :--- |
| **Google Gemini API** | 智慧教練數據分析、課表判讀與疲勞建議 | **需申請** | 免費額度足夠日常使用 | [Google AI Studio](https://aistudio.google.com/) 申請 API Key |
| **Telegram Bot API** | 每日分析報表推播至手機 Telegram | **需申請** | 完全免費 | 透過 Telegram [@BotFather](https://t.me/botfather) 建立機器人 |
| **Garmin Connect** | 取得手錶同步之活動、分圈與高階動態數據 | **無需特別申請** | 免費 | 使用個人 Garmin Connect 帳號密碼 |
| **Open-Meteo API** | 依活動 GPS 與時間查詢歷史氣溫與濕度 | **免申請 / 免 Key** | 開源免費 (非商業每日萬次) | 免註冊直接調用 [Open-Meteo Docs](https://open-meteo.com/) |

---

### 1. 🤖 Google Gemini API Key 申請教學
Gemini API 提供頂尖的生成式 AI 推理能力，用於深度解析跑者的各維度數據。

1. **前往申請網站**：瀏覽 [Google AI Studio (https://aistudio.google.com/)](https://aistudio.google.com/)。
2. **登入帳號**：使用您的個人 Google 帳號登入。
3. **建立 API Key**：
   - 點選左上角選單的 **「Get API key」** 按鈕。
   - 點擊 **「Create API key」**。
   - 選擇既有的 Google Cloud 專案，或直接選擇「Create API key in new project」自動建立新專案。
4. **複製保存**：系統將產生一串以 `AIzaSy...` 開頭的金鑰字串，複製並妥善保管，此即為 `GEMINI_API_KEY`。
5. **官方參考教學**：
   - [Gemini API 快速入門指南 (官方繁中)](https://ai.google.dev/gemini-api/docs/quickstart?lang=python)
   - [Google AI Studio 說明文件](https://ai.google.dev/aistudio)

---

### 2. 💬 Telegram Bot Token 與 Chat ID 取得教學
用於在 GitHub Actions 執行完畢後，透過 Telegram 即時將排程報表推送到您的手機。

#### 步驟 A：建立 Telegram 機器人取得 `TG_TOKEN`
1. 打開手機或電腦上的 Telegram，在搜尋欄搜尋官方機器人管理員：[`@BotFather`](https://t.me/botfather)（認明名字旁有藍色打勾認證標章）。
2. 點擊畫面底部的 **Start** 或發送 `/start`。
3. 發送指令 `/newbot` 開始建立新機器人。
4. 依序回答兩道問題：
   - **Name (顯示暱稱)**：輸入您喜歡的名稱（例如：`My AI Coach`）。
   - **Username (帳號代號)**：必須是全域唯一且字尾必須以 `bot` 結尾（例如：`my_runner_coach_bot`）。
5. 建立完成後，BotFather 會發送一則成功訊息，其中包含一串 **HTTP API Token**（格式例如：`7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`），此即為 `TG_TOKEN`。

#### 步驟 B：取得您的個人 `TG_CHAT_ID`
1. **重要先決條件**：在 Telegram 搜尋您剛剛建立的機器人帳號（例如 `@my_runner_coach_bot`），點進去並按下 **「Start」**（必須先主動向機器人發送第一則訊息，機器人才有權限私訊給您）。
2. 在 Telegram 搜尋欄尋找查詢 ID 的小工具：[`@userinfobot`](https://t.me/userinfobot) 或 [`@RawDataBot`](https://t.me/RawDataBot)。
3. 點擊 **Start**，機器人會立即回傳您的帳號資訊，其中的 **`Id`** 欄位（一串純數字，例如 `123456789`）即為您的 `TG_CHAT_ID`。
   > 若希望將報表推播到**群組或頻道**：請將建立好的機器人加入該群組並設為管理員，群組的 Chat ID 通常為負數（例如 `-100123456789`）。
4. **官方參考教學**：
   - [Telegram 官方機器人教學手冊 (Bots Tutorial)](https://core.telegram.org/bots/tutorial)
   - [BotFather 功能與指令清單](https://core.telegram.org/bots/features#botfather)

---

### 3. ⌚ Garmin Connect 帳號與 Token 快取機制 (`GARMIN_EMAIL`, `GARMIN_PWD`, `GARMINTOKENS_BASE64`)
* 本專案採用開源 Python 庫 [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect)，直接與 Garmin Connect 雲端伺服器進行同步。
* **無需申請企業 API**：Garmin 官方 Health API 審核門檻高且不對個人開放，本專案支援使用個人 Garmin Connect 帳號密碼進行驗證。
* **解決 GitHub Actions 雲端限流 (HTTP 429 / 卡住 4 分鐘) 必備技巧**：
  * Garmin 的 Cloudflare WAF 會對微軟 Azure（GitHub Actions 雲端執行機）的資料中心 IP 進行極為嚴格的密碼登入限流（出現 `mobile+cffi returned 429: IP rate limited by Garmin` 並重試 4 分鐘以上甚至失敗）。
  * **永久解決方案**：在您自己的電腦（家用寬頻或手機熱點，永遠不會被限流）執行本專案內建的匯出工具：
    ```bash
    python export_garmin_tokens.py
    ```
  * 登入後將自動產生一串 Base64 加密字串，將其複製並貼入 GitHub Secrets 的 `GARMINTOKENS_BASE64`。
  * 設定後，雲端排程將**完全跳過帳密 SSO 驗證**，每次執行皆在 **1 秒內憑 Token 快速復原連線**，穩定可靠！
* **雙重驗證 (2FA) 提示**：若您的帳號開啟了 2FA，透過上述 `export_garmin_tokens.py` 本機匯出 Token 亦是唯一能讓 GitHub Actions 自動無人值守運行的最佳解法。

---

### 4. 🌤️ Open-Meteo 氣象 API 說明
* **完全免申請、免 API Key！**
* Open-Meteo 是一個高品質的開源天氣 API 平台，整合各大國家氣象局（ECMWF、NOAA、JMA、DWD）的歷史觀測模型。
* 本專案透過其 `/v1/forecast` 端口，即時利用經緯度座標與活動發生時間查詢歷史小時溫濕度。
* 免費版提供非商業用途每天高達 **10,000 次** 請求，對於每日自動分析完全充裕且永久免費。
* **官方參考網址**：
   - [Open-Meteo 官方網站](https://open-meteo.com/)
   - [Open-Meteo API 文件與參數說明](https://open-meteo.com/en/docs)

---

## 🚀 快速開始與設定 (Setup & Usage)

### 步驟 1：Fork 或 Clone 專案
```bash
git clone https://github.com/your-username/AI_Coach.git
cd AI_Coach
```

### 步驟 2：設定 Repository Secrets (金鑰與個人化參數)

#### 什麼是 GitHub Repository Secrets？
GitHub Secrets 是 GitHub 提供的加密環境變數庫。存放在這裡的帳密與金鑰享有以下最高安全性保障：
* **單向加密存儲**：一旦建立並儲存，任何人（包含您自己）都無法再點開查看原始明文。
* **自動遮蔽保護**：即便程式碼意外印出變數，GitHub Actions 在執行日誌（Log）中也會強制將其遮蔽為 `***`。
* **開源無憂**：即使專案設為公開（Public），外部訪客與 Fork 使用者也完全**無法**讀取您的 Secrets。

#### 🛠️ 新增 Secret 的操作步驟教學：
1. 進入您在 GitHub 上的本專案儲存庫頁面。
2. 點選上方導航列最右側的 **「Settings」**（若看不到請確認是否已登入專案擁有者帳號）。
3. 在左側選單中找到並點擊 **「Secrets and variables」**，在展開的子選單中選擇 **「Actions」**。
4. 在「Repository secrets」區塊右側，點擊綠色的 **「New repository secret」** 按鈕。
5. 依序填入變數：
   - **Name**：輸入 Secret 名稱（如 `GEMINI_API_KEY`，大小寫需完全一致）。
   - **Secret**：貼上該變數對應的金鑰或數值。
6. 點擊綠色 **「Add secret」** 完成新增。
7. 重複上述步驟，將下方表格中的變數逐一建立。

> 📖 **官方參考教學**：[GitHub 官方文件：在 GitHub Actions 中使用 Secrets (繁中指南)](https://docs.github.com/zh/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions)

---

#### 變數清單與預設值對照表

##### A. 核心服務與 API 認證金鑰
| Secret 名稱 | 屬性 | 說明 | 範例與填寫方式 |
| :--- | :---: | :--- | :--- |
| `GARMIN_EMAIL` | **必填** | Garmin Connect 登入信箱 | `your_account@email.com` |
| `GARMIN_PWD` | **必填** | Garmin Connect 登入密碼 | 個人 Garmin 登入密碼 |
| `GARMINTOKENS_BASE64` | **強烈推薦** | 本地匯出的 Token Base64（**免除 429 限流卡住 4 分鐘**） | 執行 `python export_garmin_tokens.py` 產出之字串 |
| `TG_TOKEN` | **必填** | Telegram Bot Token | 向 [@BotFather](https://t.me/botfather) 建立機器人取得之金鑰 |
| `TG_CHAT_ID` | **必填** | 接收訊息的 Telegram Chat ID | 透過 [@userinfobot](https://t.me/userinfobot) 查詢取得之純數字 ID |
| `GEMINI_API_KEY` | **必填** | Google Gemini API Key | 前往 [Google AI Studio](https://aistudio.google.com/) 免費建立 |

##### B. 個人化跑者背景與氣象參數（建議填寫，完全保護隱私）
> [!TIP]
> **隱私安全設計**：透過 GitHub Secrets 注入以下跑者參數，您的真實姓名、出生年、全馬成績與居住地座標**完全不會寫在公開的程式碼中**。若未設定這些 Secrets，系統亦會自動套用泛用預設值平穩運行。

| Secret 名稱 | 說明 | 預設值參考 | 範例與填寫建議 |
| :--- | :--- | :---: | :--- |
| `RUNNER_NAME` | 跑者稱呼 / 暱稱 | `Runner` | 填寫自己的稱呼，供 AI 教練抬頭與對話稱呼使用 |
| `RUNNER_BIRTH_YEAR` | 出生年份 (四位數西元) | `1985` | 用於 AI 精準推算年齡、生理衰減與心率負荷（例如 `1988`） |
| `RUNNER_PB` | 馬拉松或主要目標賽事 PB | `3:45` | 個人全馬最佳成績（例如 `3:30` 或 `4:15`），供 AI 評估強度 |
| `ZONE2_MAX_HR` | Zone 2 有氧耐力心率上限 (bpm) | `140` | 依個人心率儲備或乳酸閾值設定之有氧上限（例如 `136` 或 `142`） |
| `DEFAULT_LAT` | 預設生活圈緯度 | `25.03` | 用於跑步機或室內運動（無 GPS 軌跡）時之反查氣象備援座標 |
| `DEFAULT_LON` | 預設生活圈經度 | `121.56` | 用於跑步機或室內運動（無 GPS 軌跡）時之反查氣象備援座標 |

### 步驟 3：自訂程式預設值 (可選)
若不使用 GitHub Secrets 注入跑者參數，亦可直接於 [`config.py`](config.py) 中檢視或修改內建的備援預設值：
```python
# --- 跑者背景參數 (優先讀取環境變數，兼顧個人隱私與預設泛用值) ---
RUNNER_NAME = os.getenv("RUNNER_NAME", "Runner")
RUNNER_BIRTH_YEAR = int(os.getenv("RUNNER_BIRTH_YEAR", "1985"))
RUNNER_PB = os.getenv("RUNNER_PB", "3:45")
ZONE2_MAX_HR = int(os.getenv("ZONE2_MAX_HR", "140"))

# --- 系統與查詢參數 ---
ACTIVITIES_COUNT = int(os.getenv("ACTIVITIES_COUNT", "7"))
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "25.03"))   # 預設緯度 (室內無 GPS 活動之室外氣象備援)
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "121.56"))  # 預設經度 (室內無 GPS 活動之室外氣象備援)
```

### 步驟 4：GitHub Actions 執行、驗證與排程調整教學

#### 什麼是 GitHub Actions？
GitHub Actions 是 GitHub 內建的雲端自動化 CI/CD 平台，無需自備伺服器即可每日免費定時執行 Python 腳本。

#### 🛠️ 手動測試執行（確認設定是否正確）：
1. 點擊專案儲存庫上方的 **「Actions」** 頁籤。
   *(若是新 Fork 的專案，若畫面上出現提示按鈕「I understand my workflows, go ahead and enable them」，請點擊以啟用)*。
2. 在左側工作流程清單中，點選 **「Garmin AI Coach Report」**。
3. 在畫面右側找到 **「Run workflow」** 下拉選單。
4. 保持選擇 `Branch: main`，點擊綠色 **「Run workflow」** 按鈕。
5. 重新整理頁面，會看見正在運行的工作流程；點進去可查看即時 Log。
6. 若各項 API 與帳密設定正確，稍候約 15~30 秒，工作流程將顯示綠色打勾（Success），並且您的手機 Telegram 會立即收到最新的 AI 教練報表！

#### ⏰ 自動排程時間自訂（Cron 排程調整）：
自動排程定義在 [`.github/workflows/daily_task.yml`](.github/workflows/daily_task.yml) 檔案中：
```yaml
on:
  schedule:
    # 預設：每日 UTC 22:45 (對應台灣時間 UTC+8 為隔日早上 06:45)
    - cron: '45 22 * * *'
```
* **UTC 時間換算提示**：GitHub 伺服器一律採用 UTC 世界協調時間。
  * 若希望在**台灣時間早上 08:00** 收到報表：`08:00 - 8小時 = UTC 00:00`，設定為 `- cron: '0 0 * * *'`。
  * 若希望在**台灣時間晚上 21:30** 收到報表：`21:30 - 8小時 = UTC 13:30`，設定為 `- cron: '30 13 * * *'`。
* 📖 **實用工具與官方文件**：
  - [Crontab.guru - 視覺化 Cron 時間表達式產生器](https://crontab.guru/)
  - [GitHub Actions 快速入門 (官方繁中)](https://docs.github.com/zh/actions/writing-workflows/quickstart)
  - [GitHub Actions 排程事件語法說明 (Schedule Event)](https://docs.github.com/zh/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule)

---

## ⚠️ 免責聲明 (Disclaimer)

* 本專案為個人運動愛好者之智慧輔助工具，AI 教練之分析與處方建議僅供運動訓練參考。
* 若訓練過程身體出現不適、胸悶、關節劇烈疼痛，請以自身體感為準並尋求專業醫師或實體專業教練協助。

---

## 📄 授權 (License)

本專案採用 [MIT License](LICENSE) 授權。
