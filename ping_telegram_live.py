"""
QuantNexus V3.1 - Live Telegram Ping & Alert Verification
"""
import os
import json
import logging
import httpx
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("TelegramPinger")

def send_telegram_alert(message: str):
    token = ""
    chat_id = ""

    for cfg_file in BASE_DIR.glob("*telegram*.json"):
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            token = data.get("bot_token", data.get("token", token))
            chat_id = data.get("chat_id", data.get("channel_id", chat_id))
        except Exception:
            pass

    if not token or not chat_id:
        token = os.environ.get("NEXUS_TELEGRAM_TOKEN", token)
        chat_id = os.environ.get("NEXUS_TELEGRAM_CHAT_ID", chat_id)

    if not token or not chat_id:
        log.error("Telegram credentials (bot_token / chat_id) not found in configuration files.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        if response.status_code == 200:
            log.info("⚡ QuantNexus Telegram Ping Successful! Alert delivered.")
            return True
        else:
            log.error(f"Telegram API Error: {response.text}")
            return False
    except Exception as e:
        log.error(f"Failed to reach Telegram API: {e}")
        return False

if __name__ == "__main__":
    msg = (
        "🟢 *QuantNexus System Operational*\n"
        "-------------------------------------\n"
        "• **Fleet Status**: 3 Silos Synchronized\n"
        "• **Account ID**: `278062038` (Terminal 1 Active)\n"
        "• **Readiness**: VPIN Toxicity & SMT Engines Armed.\n"
        "• *System standing by for Monday Market Open.*"
    )
    send_telegram_alert(msg)
