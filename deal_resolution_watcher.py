# -*- coding: utf-8 -*-
"""
QUANT-NEXUS REAL-TIME TELEGRAM DEAL WATCHER (HEADLESS DAEMON)
Polls MT5 closed deals every 10 seconds and dispatches instant alerts.
"""
import time
import httpx
from datetime import datetime, timezone, timedelta
from telegram_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Pending_278041169/terminal64.exe"
TG_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

if not mt5.initialize(path=TERMINAL, portable=False):
    exit(1)

seen_deals = set()
init_from = datetime.now(timezone.utc) - timedelta(hours=2)
for d in mt5.history_deals_get(init_from, datetime.now(timezone.utc)) or []:
    seen_deals.add(d.ticket)

print(f"[+] Watcher online. Monitoring MT5 deal stream...")

while True:
    time.sleep(10)
    now = datetime.now(timezone.utc)
    deals = mt5.history_deals_get(now - timedelta(minutes=5), now) or []
    for d in deals:
        if d.ticket not in seen_deals and d.entry == 1:
            seen_deals.add(d.ticket)
            icon = "рџЋЇ [TAKE PROFIT]" if d.profit > 0 else "рџ›ЎпёЏ [STOP LOSS]"
            side = "BUY (Close Sell)" if d.type == 0 else "SELL (Close Buy)"
            msg = (
                f"{icon} <b>{d.symbol}</b> Deal #{d.ticket}\n"
                f"Action: {side} | Lots: {d.volume:.2f}\n"
                f"Exit Price: {d.price:.5f}\n"
                f"Net Profit: <b>${d.profit:+,.2f}</b>\n"
                f"Comment: {d.comment}"
            )
            try:
                httpx.post(TG_URL, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10.0)
            except Exception:
                pass

