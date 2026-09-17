import os
import sys
import json
import base64
import getpass
from pathlib import Path

def export_tokens():
    print("=" * 60)
    print("🔑 Garmin OAuth Token 本地產生與 Base64 導出工具")
    print("=" * 60)
    print("💡 說明：Garmin 伺服器會針對微軟 Azure (GitHub Actions) 雲端機房 IP")
    print("   進行嚴格的 Cloudflare 登入限流 (HTTP 429)。")
    print("   在您自己的電腦 (家用網路/手機熱點) 登入一次並匯出 Token，")
    print("   貼到 GitHub Secrets，即可讓雲端排程永久免帳密秒速登入！")
    print("=" * 60)

    try:
        from garminconnect import Garmin
    except ImportError:
        print("\n❌ 尚未安裝 garminconnect 套件！請先在終端機執行：")
        print("   pip install garminconnect requests\n")
        return

    token_dir = Path.home() / ".garminconnect"
    token_dir.mkdir(parents=True, exist_ok=True)
    tokenstore_path = str(token_dir)

    # 檢查是否已有現成 Token 檔案
    existing_tokens = list(token_dir.glob("*.json"))
    skip_login = False
    if existing_tokens:
        print(f"📁 偵測到本機已存在 {len(existing_tokens)} 個 Token 快取檔案：")
        for f in existing_tokens:
            print(f"   • {f.name}")
        ans = input("\n是否直接匯出既有 Token？([Y]/n，輸入 n 重新登入): ").strip().lower()
        if ans not in ("n", "no"):
            skip_login = True

    if not skip_login:
        # 嘗試從環境變數讀取
        email = os.getenv("GARMIN_EMAIL")
        password = os.getenv("GARMIN_PWD")

        if not email:
            email = input("請輸入 Garmin 登入 Email: ").strip()
        else:
            print(f"📧 已偵測到 Email: {email}")

        if not password:
            password = getpass.getpass("請輸入 Garmin 登入密碼 (輸入時不顯示): ").strip()
        else:
            print("🔒 已偵測到 Garmin 密碼")

        print(f"\n⏳ 正在透過本機家用網路連線 Garmin 進行登入驗證...")
        try:
            client = Garmin(email, password)
            client.login(tokenstore_path)
            print("✅ 本地登入成功！Token 已儲存至:", tokenstore_path)
        except Exception as e:
            print(f"❌ 登入失敗: {e}")
            return

    # 收集 token 目錄下所有的 token 檔案
    tokens_dict = {}
    for f in token_dir.glob("*.json"):
        tokens_dict[f.name] = f.read_text(encoding="utf-8")

    if not tokens_dict:
        for f in token_dir.iterdir():
            if f.is_file():
                tokens_dict[f.name] = f.read_text(encoding="utf-8")

    if not tokens_dict:
        print("⚠️ 找不到已生成的 Token 檔案，請確認登入狀態。")
        return

    # 打包為 Base64 字串
    raw_json = json.dumps(tokens_dict)
    b64_str = base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")

    # 輸出至本地暫存檔
    out_file = "garmin_tokens_base64.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(b64_str)

    print("\n" + "=" * 60)
    print("🎉 恭喜！Token 已成功導出並打包為 Base64 字串！")
    print(f"📄 已同步儲存至專案目錄下的: {out_file} (已設為 .gitignore 不會上傳)")
    print("=" * 60)
    print("\n📋 請複製下方這一整行 Base64 字串：\n")
    print(b64_str)
    print("\n" + "=" * 60)
    print("👉 下一步：設定到 GitHub Secrets")
    print("1. 前往您的 GitHub 儲存庫頁面")
    print("2. 點擊「Settings」->「Secrets and variables」->「Actions」")
    print("3. 點擊「New repository secret」")
    print("   • Name (名稱)  : GARMINTOKENS_BASE64")
    print("   • Secret (內容): 貼上剛才複製的 Base64 字串")
    print("4. 點擊「Add secret」保存即可！")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    export_tokens()
