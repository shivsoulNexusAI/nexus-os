"""
QUANT NEXUS ELITE WEEKLY ALPHA REPORTER (HTML ENCODED)
"""
import os
import sys
import argparse
import json
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw").strip()
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '5279761713').strip()
SHADOW_PATH = os.path.join(BASE_DIR, "shadow_portfolio.json")

def create_resilient_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def get_kronos_telemetry() -> dict:
    if os.path.exists(SHADOW_PATH):
        try:
            with open(SHADOW_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"suppressed_count": 0, "last_veto": None}

def generate_weekly_alpha_report(top_n: int = 3) -> dict:
    kronos_data = get_kronos_telemetry()
    suppressed_count = kronos_data.get("suppressed_count", 0)
    last_veto = kronos_data.get("last_veto", {})

    report_lines = [
        "👑 <b>NEXUS ELITE ALPHA REPORT (WEEKLY COMPILATION)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📅 Generated: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>",
        f"🛡️ <b>Kronos ML Veto Shield</b>: <code>{suppressed_count} chop signals suppressed</code>",
    ]

    if last_veto:
        sym = last_veto.get('symbol', 'N/A')
        reg = last_veto.get('regime', 'N/A')
        sc = last_veto.get('score', 'N/A')
        reason = last_veto.get('reason', 'N/A')
        report_lines.append(
            f"   • Latest Veto: <code>{sym}</code> ({reg}) | Edge: <code>{sc}</code>"
        )
    report_lines.extend([
        "",
        "🎯 <b>Top Gated Execution Setups</b>:",
        "",
        "ℹ️ Community telemetry idle. Operating on autonomous Kronos gating.",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔒 <i>Shivsoul Moat & Kronos Engine Telemetry</i>"
    ])
    return {"report_html": "\n".join(report_lines)}

def broadcast_to_telegram(report_text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing from environment.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": report_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    session = create_resilient_session()
    print("[*] Dispatching HTML payload to Telegram channel...")
    
    for attempt in range(1, 4):
        try:
            resp = session.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                print("🚀 Alpha Report successfully broadcasted to Telegram channel.")
                return True
            else:
                print(f"⚠️ Telegram returned status {resp.status_code}: {resp.text}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error on attempt {attempt}: {e}")
            time.sleep(2)

    return False

def main():
    parser = argparse.ArgumentParser(description="Quant Nexus Elite Weekly Alpha Reporter")
    parser.add_argument("--broadcast", "-b", action="store_true", help="Broadcast to Telegram")
    parser.add_argument("--top", "-t", type=int, default=3)
    args = parser.parse_args()

    result = generate_weekly_alpha_report(top_n=args.top)
    print(result["report_html"])

    if args.broadcast:
        broadcast_to_telegram(result["report_html"])

if __name__ == "__main__":
    main()
