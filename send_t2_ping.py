import json
import httpx
from pathlib import Path

# Point directly to Terminal 2's Telegram config
config_path = Path(r"C:\Quant-Nexus-Eng\t2_telegram_config.json")

def send_ping():
    if not config_path.exists():
        print(f"[ERROR] Config not found at {config_path}")
        return

    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    
    token = data.get("", data.get("token", data.get("bot_token")))
    chat_id = data.get("chat_id", data.get("authorized_chat_id"))

    if not token or not chat_id:
        print(f"[ERROR] Missing token or chat_id in {config_path.name}. Content was: {data}")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🟢 *QuantNexus Terminal 2 Online*\n-------------------------------------\n• **Account ID**: `278062039`\n• **Status**: Majors Grid & SMT Armed\n• **Readiness**: Standby for Monday Open.",
        "parse_mode": "Markdown"
    }

    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        if response.status_code == 200:
            print("[SUCCESS] Telegram ping successfully delivered to Terminal 2 channel!")
        else:
            print(f"[FAILED] Telegram API Error: {response.text}")
    except Exception as e:
        print(f"[ERROR] Network connection failed: {e}")

if __name__ == "__main__":
    send_ping()
