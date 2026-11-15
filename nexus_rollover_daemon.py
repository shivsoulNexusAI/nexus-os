"""
QuantNexus Midnight Rollover & Real-Time Spread Guard Daemon
Protects all terminals from spread widening and swaps during 23:55 - 00:10 broker window.
"""
import sys
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import httpx
import MetaTrader5 as mt5

sys.stdout.reconfigure(line_buffering=True)

CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\rollover_guard.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("RolloverGuard")

MT5_PATHS = [
    (r"C:\MT5_Quant_278061453\terminal64.exe", 278062038),
    (r"C:\MT5_Pending_278041169\terminal64.exe", 278062039),
    (r"C:\MT5_HFT_278041671\terminal64.exe", 278062042)
]

MAX_ALLOWED_SPREAD_POINTS = {
    "EURUSD": 35,
    "GBPUSD": 45,
    "USDJPY": 40,
    "XAUUSD": 80
}

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
        log.warning("Telegram notice failed: %s", e)

def check_spread_and_rollover():
    now_utc = datetime.now(timezone.utc)
    
    # Broker rollover check (21:55 - 22:15 UTC / 23:55 - 00:15 Server)
    is_rollover_window = (now_utc.hour == 21 and now_utc.minute >= 55) or (now_utc.hour == 22 and now_utc.minute <= 15)

    spread_warnings = []
    
    # Interrogate spreads via T1
    if mt5.initialize(path=MT5_PATHS[0][0]):
        for sym, max_pts in MAX_ALLOWED_SPREAD_POINTS.items():
            info = mt5.symbol_info(sym)
            if info:
                spread = info.spread
                if spread > max_pts:
                    spread_warnings.append(f"{sym}: {spread} pts (Limit: {max_pts})")
        mt5.shutdown()

    state = {
        "timestamp": now_utc.isoformat(),
        "is_rollover_window": is_rollover_window,
        "spread_warnings": spread_warnings,
        "trading_permitted": not (is_rollover_window or len(spread_warnings) >= 2)
    }

    # Write state file for other daemons to consume
    state_file = Path(r"C:\Quant-Nexus-Eng\rollover_state.json")
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if is_rollover_window:
        log.warning("[ROLLOVER LOCKOUT] Active rollover settlement period. High-risk executions suspended.")
    elif spread_warnings:
        log.warning("[SPREAD EXPANSION] Abnormal spreads detected: %s", ", ".join(spread_warnings))

if __name__ == "__main__":
    log.info("Starting QuantNexus Rollover & Spread Guard Daemon...")
    while True:
        try:
            check_spread_and_rollover()
        except Exception as e:
            log.error("Rollover loop exception: %s", e)
        time.sleep(10)
