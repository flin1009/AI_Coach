import os
import requests
from config import TG_TOKEN, TG_CHAT_ID

def send_telegram(text, parse_mode=None):
    """發送訊息至 Telegram (支援可選 parse_mode，長度超過 4000 字元時自動分段)
    具備容錯降級：若 HTML 格式傳送失敗，自動切換純文字重發，確保訊息絕對送達。
    """
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram 設定不完整，無法發送")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    
    # 分段處理
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)] if len(text) > 4000 else [text]
    
    for chunk in chunks:
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
