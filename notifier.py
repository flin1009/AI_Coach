import os
import re
import time
import requests
from config import TG_TOKEN, TG_CHAT_ID

def split_telegram_text(text, max_chars=4000):
    """依據條件將訊息拆分為多則發送：
    1. 條件切分：若包含【Gemini AI 教練建議】或【Gemini 休整與超補償指引】，
       自動將前面的「個人資訊與訓練數據」切為第一則，第二則自【Gemini...】開始。
    2. 字數安全切分：每一則訊息若長度超過 max_chars (預設 4000 字元)，自動再按字數分段。
    """
    if not text:
        return []

    # 尋找第一階段邏輯切分點 (保留 emoji 與標題)
    pattern = r'(\n*(?:🤖\s*)?【Gemini[^】]*】)'
    match = re.search(pattern, text)

    primary_sections = []
    if match:
        split_idx = match.start()
        part1 = text[:split_idx].strip()
        part2 = text[split_idx:].strip()
        if part1:
            primary_sections.append(part1)
        if part2:
            primary_sections.append(part2)
    else:
        primary_sections = [text.strip()]

    # 第二階段：對每一則進行字數確認自動切分
    final_chunks = []
    for section in primary_sections:
        if len(section) > max_chars:
            chunks = [section[i:i+max_chars] for i in range(0, len(section), max_chars)]
            final_chunks.extend(chunks)
        else:
            final_chunks.append(section)

    return final_chunks

def send_telegram(text, parse_mode=None):
    """發送訊息至 Telegram (支援條件分段 + 4000 字元長度自動切分)
    1. 條件切分：將跑者資訊與活動數據切為第一則，自【Gemini AI 教練建議】開始切為第二則。
    2. 字數切分：每則長度若超過 4000 字元，自動依字數再分段發送。
    3. 具備容錯降級：若 HTML 格式傳送失敗，自動切換純文字重發，確保訊息絕對送達。
    """
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram 設定不完整，無法發送")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    
    # 執行條件切分與字數安全切分
    chunks = split_telegram_text(text, max_chars=4000)
    
    for idx, chunk in enumerate(chunks):
        payload = {"chat_id": TG_CHAT_ID, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            res = requests.post(url, data=payload, timeout=10)
            if res.status_code != 200 and parse_mode:
                # 若因 HTML 標籤格式錯誤被 Telegram 拒絕，自動降級為純文字發送
                print(f"⚠️ Telegram {parse_mode} 模式發送異常 (HTTP {res.status_code})，自動降級為純文字發送...")
                payload.pop("parse_mode", None)
                fallback_res = requests.post(url, data=payload, timeout=10)
                if fallback_res.status_code != 200:
                    print(f"❌ Telegram 純文字重發失敗: {fallback_res.text}")
            elif res.status_code != 200:
                print(f"❌ Telegram 發送失敗: {res.text}")
        except Exception as e:
            print(f"Telegram 發送異常: {e}")
        
        # 若有多則訊息，間隔 0.5 秒確保 Telegram 按時序正確接收
        if len(chunks) > 1 and idx < len(chunks) - 1:
            time.sleep(0.5)

def send_telegram_photo(photo_path, caption=None):
    """發送圖片至 Telegram (支援可選文字圖說 caption)"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram 設定不完整，無法發送圖片")
        return False
    if not photo_path or not os.path.exists(photo_path):
        print(f"⚠️ 圖表檔案不存在: {photo_path}")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": TG_CHAT_ID}
            if caption:
                data["caption"] = caption[:1024]
            res = requests.post(url, data=data, files=files, timeout=25)
            if res.status_code == 200:
                print("📸 視覺化圖表已成功推播至 Telegram！")
                return True
            else:
                print(f"❌ Telegram 圖片發送失敗: {res.text}")
                return False
    except Exception as e:
        print(f"Telegram 圖片發送異常: {e}")
        return False
