# -*- coding: utf-8 -*-
"""
QUANT-NEXUS RAPID PROFIT PROTECTION & DYNAMIC TRAILING ENGINE
Dedicated to Account #278041169 (Silo 2) & #278017866 (Silo 1)
"""
import os
import sys
import json
import time
import math
import logging
from pathlib import Path
import MetaTrader5 as mt5

LOG_FILE = Path(r"C:\Quant-Nexus-Prod\core\breakeven_engine.log")
STATE_PATH = Path(r"C:\Quant-Nexus-Prod\core\breakeven_state.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("BreakevenEngine")

SILOS = [
    {
        "name": "Silo 2 (Nexus AI Bot)",
        "login": 278041169,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:/MT5_Quant_278017866/terminal64.exe",
        "portable": False
    },
    {
        "name": "Silo 1 (Silver Bullet)",
        "login": 278017866,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe",
        "portable": False
    }
]

SPREAD_PAD_POINTS = {
    "EURUSD": 12,
    "GBPUSD": 15,
    "USDJPY": 15,
    "XAUUSD": 60,
    "BTCUSD": 300,
    "US30": 30
}

scaled_tickets = set()

def load_state():
    global scaled_tickets
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                scaled_tickets = set(data.get("scaled_tickets", []))
        except Exception as e:
            log.warning("Error loading BE state: %s", e)

def save_state():
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"scaled_tickets": list(scaled_tickets)}, f, indent=2)
    except Exception as e:
        log.warning("Error saving BE state: %s", e)

def get_supported_filling(symbol):
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return mt5.ORDER_FILLING_IOC
    modes = sym_info.filling_mode
    if modes & 1:
        return mt5.ORDER_FILLING_FOK
    elif modes & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def audit_silo(silo):
    path = silo["path"]
    login = silo["login"]
    portable = silo["portable"]

    if not mt5.initialize(path=path, portable=portable):
        log.warning("MT5 Init failed for %s: %s", silo["name"], mt5.last_error())
        return

    acc = mt5.account_info()
    if not acc or acc.login != login:
        if not mt5.login(login=login, password=silo["password"], server=silo["server"]):
            log.warning("Login failed for %s (#%s): %s", silo["name"], login, mt5.last_error())
            mt5.shutdown()
            return

    positions = mt5.positions_get() or []
    if not positions:
        mt5.shutdown()
        return

    active_tickets = {p.ticket for p in positions}
    dead_tickets = scaled_tickets - active_tickets
    if dead_tickets:
        scaled_tickets.difference_update(dead_tickets)
        save_state()

    for p in positions:
        ticket = p.ticket
        sym = p.symbol
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        open_price = float(p.price_open)
        mark = float(p.price_current)
        sl = float(p.sl)
        volume = float(p.volume)

        sym_info = mt5.symbol_info(sym)
        if not sym_info:
            continue

        digits = sym_info.digits
        point = sym_info.point
        pad_pts = SPREAD_PAD_POINTS.get(sym.rstrip("m"), 20)
        spread_pad = pad_pts * point

        if sl > 0 and abs(open_price - sl) > spread_pad:
            initial_risk = abs(open_price - sl)
        else:
            initial_risk = 200 * point

        gain = (mark - open_price) if is_buy else (open_price - mark)
        r_mult = gain / initial_risk if initial_risk > 0 else 0.0

        # === TIER 1: RAPID BREAKEVEN LOCK (+0.75R) ===
        if r_mult >= 0.75:
            target_be_sl = round(open_price + spread_pad if is_buy else open_price - spread_pad, digits)
            needs_be_lock = False
            eps = 0.5 * point

            if is_buy and ((target_be_sl - sl) > eps or sl == 0.0):
                needs_be_lock = True
            elif not is_buy and ((sl - target_be_sl) > eps or sl == 0.0):
                needs_be_lock = True

            if needs_be_lock:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "symbol": sym,
                    "sl": target_be_sl,
                    "tp": p.tp
                }
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log.info("[TIER 1 BE-LOCK] #%s (%s) at +%.2fR -> SL locked at %s", ticket, sym, r_mult, target_be_sl)
                    sl = target_be_sl

        # === TIER 2: RAPID HARVEST (+1.40R for positions >= 0.02 lots) ===
        if r_mult >= 1.40 and ticket not in scaled_tickets:
            step = sym_info.volume_step
            min_lot = sym_info.volume_min
            half_vol = round(math.floor((volume / 2.0) / step) * step, 2)

            if half_vol >= min_lot and (volume - half_vol) >= min_lot:
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                close_price = sym_info.bid if is_buy else sym_info.ask
                close_filling = get_supported_filling(sym)

                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": ticket,
                    "symbol": sym,
                    "volume": half_vol,
                    "type": close_type,
                    "price": close_price,
                    "deviation": 20,
                    "magic": p.magic,
                    "comment": "Nexus_Rapid_Harvest_1.4R",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": close_filling
                }
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    scaled_tickets.add(ticket)
                    save_state()
                    log.info("[TIER 2 HARVEST] #%s (%s) locked 50%% (%.2fL) at +%.2fR", ticket, sym, half_vol, r_mult)

        # === TIER 3: DYNAMIC M5 CANDLE TRAILING STOP (Activates >= +1.2R or post-harvest) ===
        if r_mult >= 1.20 or ticket in scaled_tickets:
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 1, 2)
            if rates is not None and len(rates) >= 2:
                if is_buy:
                    lowest_low = min(rates[0]["low"], rates[1]["low"])
                    proposed_sl = round(lowest_low - spread_pad, digits)
                    if proposed_sl > sl and proposed_sl > (open_price + spread_pad):
                        mt5.order_send({
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "symbol": sym,
                            "sl": proposed_sl,
                            "tp": p.tp
                        })
                        log.info("[TIER 3 TRAIL] #%s (%s BUY) SL trailed upward to %s", ticket, sym, proposed_sl)
                else:
                    highest_high = max(rates[0]["high"], rates[1]["high"])
                    proposed_sl = round(highest_high + spread_pad, digits)
                    if (sl == 0.0 or proposed_sl < sl) and proposed_sl < (open_price - spread_pad):
                        mt5.order_send({
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "symbol": sym,
                            "sl": proposed_sl,
                            "tp": p.tp
                        })
                        log.info("[TIER 3 TRAIL] #%s (%s SELL) SL trailed downward to %s", ticket, sym, proposed_sl)

    mt5.shutdown()

def main():
    log.info("Starting Refined Fast-Protection Breakeven & Trailing Engine...")
    load_state()
    while True:
        try:
            for silo in SILOS:
                audit_silo(silo)
        except Exception as e:
            log.error("Breakeven cycle exception: %s", e)
        time.sleep(3)

if __name__ == "__main__":
    main()