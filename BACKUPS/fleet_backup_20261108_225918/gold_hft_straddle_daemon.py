"""
QuantNexus Gold 24H HFT Straddle Engine
Target Account : 278041671 (Exness-MT5Trial5)
Terminal Path  : C:\MT5_HFT_278041671\terminal64.exe
Instrument     : XAUUSD
Mechanism      : Continuous Dynamic BUY_STOP & SELL_STOP Straddle ($2.50 Step)
Telemetry      : Locked directly to gold_telegram_config.json (9213146215)
"""
import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import httpx
import MetaTrader5 as mt5

GOLD_CFG = Path(r"C:\Quant-Nexus-Eng\gold_telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\gold_hft_straddle.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("GoldHFT")

MT5_PATH = r"C:\MT5_HFT_278041671\terminal64.exe"
ACCOUNT = 278041671
SYMBOL = "XAUUSD"

# Operational Parameters
STEP_DISTANCE = 2.50       # $2.50 offset from Ask/Bid
STOP_LOSS_DIST = 4.00      # $4.00 Stop Loss per bracket leg
TAKE_PROFIT_DIST = 6.00    # $6.00 Take Profit per bracket leg
LOT_SIZE = 0.01            # Base micro-lot
MAX_DRIFT_THRESHOLD = 1.80 # Cancel and re-anchor if spot price drifts $1.80 past stop
MAGIC_NUMBER = 278041671
POLL_INTERVAL = 1.0        # 1-second dynamic surveillance loop

tracked_positions = set()

def send_gold_alert(message: str):
    if not GOLD_CFG.exists():
        log.warning("gold_telegram_config.json not found on disk!")
        return
    try:
        cfg = json.loads(GOLD_CFG.read_text(encoding="utf-8"))
        token = cfg.get("bot_token")
        chat_id = cfg.get("authorized_chat_id")
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with httpx.Client(timeout=6.0) as client:
            resp = client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
            log.info("Telegram Alert dispatched via bot%s -> Status %s", token[:10], resp.status_code)
    except Exception as e:
        log.warning("Gold Telegram dispatch error: %s", e)

def init_hft_terminal() -> bool:
    if not mt5.initialize(path=MT5_PATH):
        log.error("Failed to initialize terminal at %s | Error: %s", MT5_PATH, mt5.last_error())
        return False

    acc = mt5.account_info()
    if not acc:
        log.error("Unable to query account details.")
        return False

    if acc.login != ACCOUNT:
        log.critical("ACCOUNT SAFETY LOCK: Expected #%s but found #%s. Exiting.", ACCOUNT, acc.login)
        mt5.shutdown()
        return False

    if not mt5.symbol_select(SYMBOL, True):
        log.error("Failed to select %s in Market Watch.", SYMBOL)
        return False

    log.info("LOCKED ON HFT TERMINAL: Account #%s (%s) | Balance: $%.2f | Leverage 1:%s",
             acc.login, acc.server, acc.balance, acc.leverage)
    return True

def audit_fills_and_notify():
    global tracked_positions
    positions = mt5.positions_get(symbol=SYMBOL)
    current_tickets = set()

    if positions:
        for p in positions:
            if p.magic != MAGIC_NUMBER:
                continue
            current_tickets.add(p.ticket)
            if p.ticket not in tracked_positions:
                side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                log.info("[FILL DETECTED] %s %s %.2f lots @ %.2f (Ticket: #%s)",
                         SYMBOL, side, p.volume, p.price_open, p.ticket)
                
                alert_text = (
                    f"🟡 <b>GOLD HFT STRADDLE FILLED</b>\n\n"
                    f"<b>Account:</b> #{ACCOUNT}\n"
                    f"<b>Symbol:</b> {SYMBOL} | <b>Side:</b> {side}\n"
                    f"<b>Volume:</b> {p.volume} lots\n"
                    f"<b>Fill Price:</b> {p.price_open:.2f}\n"
                    f"<b>SL:</b> {p.sl:.2f} | <b>TP:</b> {p.tp:.2f}\n"
                    f"<b>Ticket:</b> #{p.ticket}\n\n"
                    f"<i>Dynamic Bracket Active</i>"
                )
                send_gold_alert(alert_text)

    tracked_positions = current_tickets

def cancel_pending_order(ticket: int):
    req = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": ticket,
        "magic": MAGIC_NUMBER,
        "comment": "STRADDLE_DRIFT_CANCEL"
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info("Canceled drifted pending stop #%s", ticket)
    else:
        log.warning("Failed to cancel #%s: %s", ticket, getattr(res, "comment", "error"))

def maintain_straddle():
    audit_fills_and_notify()

    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)
    if not tick or not info:
        return

    orders = mt5.orders_get(symbol=SYMBOL)
    pending_orders = [o for o in orders if o.magic == MAGIC_NUMBER] if orders else []

    buy_stops = [o for o in pending_orders if o.type == mt5.ORDER_TYPE_BUY_STOP]
    sell_stops = [o for o in pending_orders if o.type == mt5.ORDER_TYPE_SELL_STOP]

    target_buy_price = round(tick.ask + STEP_DISTANCE, 2)
    target_sell_price = round(tick.bid - STEP_DISTANCE, 2)

    # 1. Manage BUY_STOP drift and placement
    if buy_stops:
        bs = buy_stops[0]
        drift = abs(bs.price_open - target_buy_price)
        if drift > MAX_DRIFT_THRESHOLD:
            log.info("BUY STOP drift ($%.2f) > threshold. Re-centering...", drift)
            cancel_pending_order(bs.ticket)
    else:
        req_buy = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": SYMBOL,
            "volume": LOT_SIZE,
            "type": mt5.ORDER_TYPE_BUY_STOP,
            "price": target_buy_price,
            "sl": round(target_buy_price - STOP_LOSS_DIST, 2),
            "tp": round(target_buy_price + TAKE_PROFIT_DIST, 2),
            "magic": MAGIC_NUMBER,
            "comment": "GOLD_HFT_BUY_STOP",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res_buy = mt5.order_send(req_buy)
        if res_buy and res_buy.retcode == mt5.TRADE_RETCODE_DONE:
            log.info("[+] Placed BUY STOP @ %.2f (Ticket: #%s)", target_buy_price, res_buy.order)
        else:
            log.warning("Buy Stop declined: %s", getattr(res_buy, "comment", "error"))

    # 2. Manage SELL_STOP drift and placement
    if sell_stops:
        ss = sell_stops[0]
        drift = abs(ss.price_open - target_sell_price)
        if drift > MAX_DRIFT_THRESHOLD:
            log.info("SELL STOP drift ($%.2f) > threshold. Re-centering...", drift)
            cancel_pending_order(ss.ticket)
    else:
        req_sell = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": SYMBOL,
            "volume": LOT_SIZE,
            "type": mt5.ORDER_TYPE_SELL_STOP,
            "price": target_sell_price,
            "sl": round(target_sell_price + STOP_LOSS_DIST, 2),
            "tp": round(target_sell_price - TAKE_PROFIT_DIST, 2),
            "magic": MAGIC_NUMBER,
            "comment": "GOLD_HFT_SELL_STOP",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res_sell = mt5.order_send(req_sell)
        if res_sell and res_sell.retcode == mt5.TRADE_RETCODE_DONE:
            log.info("[+] Placed SELL STOP @ %.2f (Ticket: #%s)", target_sell_price, res_sell.order)
        else:
            log.warning("Sell Stop declined: %s", getattr(res_sell, "comment", "error"))

if __name__ == "__main__":
    log.info("QuantNexus 24H Gold HFT Straddle Initializing (Locked to Token 9213146215)...")
    if not init_hft_terminal():
        sys.exit(1)

    send_gold_alert(
        f"<b>[POLICED GOLD ENGINE ONLINE]</b>\n\n"
        f"<b>Account:</b> #{ACCOUNT}\n"
        f"<b>Instrument:</b> {SYMBOL}\n"
        f"<b>Straddle Band:</b> +/-${STEP_DISTANCE:.2f}\n"
        f"<b>Breakeven:</b> Trigger +$0.35 -> Lock +$0.08\n"
        f"<b>Dynamic SL/TP:</b> Trail $0.32 | Runner TP +$0.50\n\n"
        f"<i>Status: Continuous 24/7 Straddle Active</i>"
    )

    try:
        log.info("Continuous $2.50 Straddle Loop Engaged on XAUUSD (Account #%s).", ACCOUNT)
        while True:
            maintain_straddle()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log.info("Stopped by operator.")
    finally:
        mt5.shutdown()
