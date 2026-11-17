"""
SHIVSOUL NEXUS // TELEGRAM DIRECT API CONNECTION TEST
- Verifies bot token authentication and tests dispatch payload delivery.
"""

import json
from pathlib import Path
import httpx

CONFIG_PATH = Path(r"C:\Quant-Nexus-Eng\t1_telegram_config.json")

def test_telegram():
    if not CONFIG_PATH.exists():
        print(f"[ERR] Configuration file not found at {CONFIG_PATH}")
        return

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"[ERR] Failed to parse JSON config: {e}")
        return

    bot_token = config.get("bot_token") or config.get("token")
    chat_id = config.get("chat_id")

    if not bot_token or not chat_id:
        print("[ERR] 'bot_token' or 'chat_id' missing from t1_telegram_config.json")
        return

    print(f"=== TESTING TELEGRAM DISPATCH ===")
    print(f"Target Chat ID : {chat_id}")
    
    # 1. Test getMe to verify bot token validity
    me_url = f"https://api.telegram.org/bot{bot_token}/getMe"
    try:
        res = httpx.get(me_url, timeout=10.0)
        data = res.json()
        if data.get("ok"):
            bot_name = data["result"].get("username", "UnknownBot")
            print(f"[OK] Bot Token Authenticated! Bot Username: @{bot_name}")
        else:
            print(f"[ERR] Bot authentication failed: {data}")
            return
    except Exception as e:
        print(f"[ERR] Network error connecting to Telegram API: {e}")
        return

    # 2. Test sendMessage dispatch
    msg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🟢 [SHIVSOUL NEXUS v9.0] Direct Telegram Telemetry Test: Fleet dispatch operational and synchronized!"
    }

    try:
        res = httpx.post(msg_url, json=payload, timeout=10.0)
        data = res.json()
        if data.get("ok"):
            print("[SUCCESS] Test message successfully delivered to Telegram channel/chat!")
        else:
            print(f"[ERR] Failed to send message: {data}")
    except Exception as e:
        print(f"[ERR] Exception during message dispatch: {e}")

if __name__ == "__main__":
    test_telegram()
