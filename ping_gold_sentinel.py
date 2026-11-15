import httpx
from telegram_gold_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TARGET_LOGIN

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": (
        f"🥇 <b>[MISSION CHARLIE: GOLD SENTINEL FULLY ACTIVE]</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Account:</b> #{TARGET_LOGIN} (Dedicated HFT Terminal)\n"
        f"<b>Daemon Process:</b> PID 8796 (Online & Headless)\n"
        f"<b>Strategy:</b> ATR Dynamic Volatility Straddle + Chop Sentinel\n"
        f"<b>Protection:</b> Rollover Gap & Asian Spread Expansion Shield Enabled\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ All execution events will report directly to this channel."
    ),
    "parse_mode": "HTML"
}
r = httpx.post(url, json=payload, timeout=8.0)
print(f"[{'SUCCESS' if r.status_code == 200 else 'FAILED'}] Gold Sentinel Telemetry Ping: HTTP {r.status_code}")