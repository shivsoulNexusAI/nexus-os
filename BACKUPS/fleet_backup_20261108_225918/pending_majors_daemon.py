"""
Nexus AI Bot Telemetry Daemon for Terminal 2 (#278041169)
Target Account : 278041169 (Exness-MT5Trial5)
Terminal Path  : C:\MT5_Pending_278041169\terminal64.exe
Assets         : EURUSD, GBPUSD, USDJPY, US30
Telemetry Pipe : Dedicated @Nexus_AIk_bot (8578781048)
"""
import os
import sys
import time
import json
import logging
from pathlib import Path
import httpx
import MetaTrader5 as mt5

CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\pending_majors_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\pending_majors_telemetry.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("PendingMajors")

MT5_PATH = r"C:\MT5_Pending_278041169\terminal64.exe"
ACCOUNT = 278041169
POLL_INTERVAL = 2.0

tracked_positions = set()

def load_config():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("bot_token"), data.get("authorized_chat_id")
    except Exception:
        return None, None

def send_nexus_ai_alert(message: str):
    token, chat_id = load_config()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=6.0) as client:
            client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        log.warning("Telegram dispatch error: %s", e)

def init_terminal() -> bool:
    if not mt5.initialize(path=MT5_PATH):
        log.error("Failed to initialize terminal at %s | Error: %s", MT5_PATH, mt5.last_error())
        return False

    acc = mt5.account_info()
    if not acc:
        log.error("Failed to retrieve account details.")
        return False

    if acc.login != ACCOUNT:
        log.critical("ACCOUNT SAFETY GUARD: Expected #%s, got #%s. Aborting.", ACCOUNT, acc.login)
        mt5.shutdown()
        return False

    log.info("LOCKED ON TERMINAL: Account #%s (%s) | Balance: $%.2f | Floating Equity: $%.2f",
             acc.login, acc.server, acc.balance, acc.equity)
    return True

def audit_book_and_notify():
    global tracked_positions
    positions = mt5.positions_get()
    current_tickets = set()

    if positions:
        for p in positions:
            current_tickets.add(p.ticket)
            if p.ticket not in tracked_positions:
                side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                log.info("[FILL DETECTED] %s %s %.2f lots @ %.5f (Ticket: #%s)",
                         p.symbol, side, p.volume, p.price_open, p.ticket)
                
                msg = (
                    f"👑 <b>NEXUS AI BOT // ORDER FILLED</b>\n\n"
                    f"<b>Account:</b> <code>#{ACCOUNT}</code>\n"
                    f"<b>Asset:</b> <code>{p.symbol}</code> | <b>Side:</b> {side}\n"
                    f"<b>Volume:</b> <code>{p.volume}</code> lots\n"
                    f"<b>Entry Price:</b> <code>{p.price_open}</code>\n"
                    f"<b>SL:</b> <code>{p.sl}</code> | <b>TP:</b> <code>{p.tp}</code>\n"
                    f"<b>Ticket:</b> <code>#{p.ticket}</code>\n\n"
                    f"<i>Pending Breakout Straddle Triggered</i>"
                )
                send_nexus_ai_alert(msg)

    tracked_positions = current_tickets

if __name__ == "__main__":
    log.info("Starting Nexus AI Bot Telemetry Daemon for Account #%s...", ACCOUNT)
    if not init_terminal():
        sys.exit(1)

    acc = mt5.account_info()
    positions = mt5.positions_get()
    orders = mt5.orders_get()
    
    # Pre-populate existing positions
    if positions:
        tracked_positions = {p.ticket for p in positions}

    online_msg = (
        f"👑🔥 <b>NEXUS AI BOT ONLINE</b>\n\n"
        f"<b>Account:</b> <code>#{ACCOUNT}</code> (Exness-MT5Trial5)\n"
        f"<b>Balance:</b> <code>${acc.balance:.2f}</code> | <b>Equity:</b> <code>${acc.equity:.2f}</code>\n"
        f"<b>Active Trades:</b> <code>{len(positions) if positions else 0}</code>\n"
        f"<b>Pending Orders on Book:</b> <code>{len(orders) if orders else 0}</code>\n\n"
        f"<i>Surveillance Active across 4 Majors & Indices</i>"
    )
    send_nexus_ai_alert(online_msg)

    try:
        while True:
            audit_book_and_notify()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log.info("Stopped by operator.")
    finally:
        mt5.shutdown()
