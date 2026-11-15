import os
import json
import httpx
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")

def load_telegram_credentials():
    token = None
    chat_id = None
    
    # Search all JSON config files in the project directory
    for cfg_file in BASE_DIR.glob("*.json"):
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            # Check for various common key names used across your configs
            token = data.get("bot_token", data.get("token", token))
            chat_id = data.get("chat_id", data.get("channel_id", data.get("telegram_chat_id", chat_id)))
            if token and chat_id:
                print(f"[INFO] Loaded credentials from: {cfg_file.name}")
                break
        except Exception:
            pass
            
    return token, chat_id

def test_ping():
    token, chat_id = load_telegram_credentials()
    
    if not token or not chat_id:
        print("[ERROR] Could not automatically find bot_token and chat_id in any JSON config files!")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🟢 *QuantNexus Direct Ping Successful!*\n• System is wired to Terminal 1 (`278062038`)\n• VPIN & SMT Engines Armed\n• Ready for Monday Market Open.",
        "parse_mode": "Markdown"
    }
    
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        if response.status_code == 200:
            print("[SUCCESS] Telegram alert sent successfully! Check your channel.")
        else:
            print(f"[FAILED] Telegram API Error: {response.text}")
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")

if __name__ == "__main__":
    test_ping()
