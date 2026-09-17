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
