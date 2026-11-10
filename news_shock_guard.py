# -*- coding: utf-8 -*-
"""
QuantNexus Mission Bravo: High-Impact Macro Economic News Sentinel
Polls economic calendar feeds for Red-Folder events across USD, EUR, GBP, JPY.
Enforces a 30-minute freeze window (T-15m to T+15m) to protect the fleet from slippage.
"""
import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx

CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\news_guard.log")
LOCKOUT_STATE_FILE = Path(r"C:\Quant-Nexus-Eng\news_lockout.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("NewsShockGuard")

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
TARGET_CURRENCIES = {"USD", "EUR", "GBP", "JPY"}
PRE_NEWS_MINUTES = 15
POST_NEWS_MINUTES = 15

def load_telegram_cfg():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("bot_token"), data.get("authorized_chat_id")
    except Exception:
        return None, None

def send_alert(msg: str):
    token, chat_id = load_telegram_cfg()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=8.0) as client:
            client.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        log.warning("Telegram alert failed: %s", e)

def fetch_calendar_events():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.get(CALENDAR_URL, headers=headers)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        log.warning("Calendar fetch error: %s", e)
    return []

def evaluate_quarantine():
    events = fetch_calendar_events()
    now_utc = datetime.now(timezone.utc)
    
    in_lockout = False
    active_threats = []
    upcoming_events = []

    for ev in events:
        impact = ev.get("impact", "")
        currency = ev.get("country", "")
        title = ev.get("title", "")
        ev_date_str = ev.get("date", "")

        # Target only Red Folder (High Impact) events on our traded currencies
        if impact.lower() != "high" or currency not in TARGET_CURRENCIES:
            continue

        try:
            # Parse ISO date with timezone awareness
            ev_dt = datetime.fromisoformat(ev_date_str.replace("Z", "+00:00"))
            time_diff = (ev_dt - now_utc).total_seconds() / 60.0

            # Within quarantine window: -15 mins to +15 mins
            if -POST_NEWS_MINUTES <= time_diff <= PRE_NEWS_MINUTES:
                in_lockout = True
                active_threats.append({
                    "currency": currency,
                    "title": title,
                    "event_time": ev_dt.strftime("%H:%M UTC"),
                    "mins_away": int(time_diff)
                })
            # Track events occurring within the next 4 hours
            elif 0 < time_diff <= 240:
                upcoming_events.append({
                    "currency": currency,
                    "title": title,
                    "event_time": ev_dt.strftime("%H:%M UTC"),
                    "mins_away": int(time_diff)
                })
        except Exception:
            continue

    state = {
        "timestamp": now_utc.isoformat(),
        "quarantine_active": in_lockout,
        "active_threats": active_threats,
        "upcoming_events": upcoming_events[:3]
    }
    
    LOCKOUT_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state

def sentinel_loop():
    log.info("Starting Mission Bravo: High-Impact Macro Economic News Sentinel...")
    alerted_threats = set()

    while True:
        try:
            state = evaluate_quarantine()
            active = state.get("active_threats", [])
            
            if state["quarantine_active"]:
                log.warning("[NEWS LOCKOUT ENGAGED] Fleet execution frozen for: %s", [t['title'] for t in active])
                for t in active:
                    threat_key = f"{t['currency']}_{t['title']}_{t['event_time']}"
                    if threat_key not in alerted_threats:
                        alert_msg = (
                            f"⚠️ <b>[MACRO SHOCK QUARANTINE ENGAGED]</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"<b>Event:</b> <code>{t['currency']} - {t['title']}</code>\n"
                            f"<b>Release Time:</b> <code>{t['event_time']}</code>\n"
                            f"<b>Status:</b> 🚨 T{t['mins_away']:+d}m Window Active\n"
                            f"<b>Action:</b> Signal generation suppressed across T1, T2, T3.\n"
                            f"<i>Resumes automatically 15m post-release.</i>"
                        )
                        send_alert(alert_msg)
                        alerted_threats.add(threat_key)
            else:
                log.info("Macro Calendar Clear. No active red-folder events in window.")

        except Exception as e:
            log.error("Sentinel loop exception: %s", e)
            
        time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        st = evaluate_quarantine()
        print("=" * 60)
        print("[*] MACRO CALENDAR EVALUATION PROBE:")
        print(f"    • Quarantine Active: {st['quarantine_active']}")
        print(f"    • Active Threats: {len(st['active_threats'])}")
        for th in st['active_threats']:
            print(f"       -> [{th['currency']}] {th['title']} at {th['event_time']} ({th['mins_away']}m)")
        print(f"    • Upcoming Red Folders: {len(st['upcoming_events'])}")
        for up in st['upcoming_events']:
            print(f"       -> [{up['currency']}] {up['title']} at {up['event_time']} (in {up['mins_away']}m)")
        print("=" * 60)
    else:
        sentinel_loop()