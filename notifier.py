import requests
from config import TG_TOKEN, TG_CHAT_ID

def send_telegram(text):
    """發送訊息至 Telegram (長度超過 4000 字元時自動分段)"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram 設定不完整，無法發送")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text[i:i+4000]})
        else:
            requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text})
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")
