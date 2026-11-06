import os
import json
import time
import math
import MetaTrader5 as mt5

LOGIN = 278017866
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"

STATE_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\breakeven_state.json"

SPREAD_PAD_POINTS = {
    "EURUSD": 15,
    "GBPUSD": 20,
    "USDJPY": 20,
    "XAUUSD": 75,
    "BTCUSD": 150
}

scaled_tickets = set()

def load_state():
    global scaled_tickets
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                scaled_tickets = set(data.get("scaled_tickets", []))
        except Exception:
            pass

def save_state():
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"scaled_tickets": list(scaled_tickets)}, f, indent=2)
    except Exception:
        pass

def ensure_mt5():
    if not mt5.terminal_info():
        mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe")
        mt5.login(login=LOGIN, password=PASSWORD, server=SERVER)

def get_filling_mode(symbol):
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return mt5.ORDER_FILLING_FOK
    modes = sym_info.filling_mode
    if modes & 2:
        return mt5.ORDER_FILLING_IOC
    elif modes & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN

def process_active_positions():
    load_state()
    ensure_mt5()
    positions = mt5.positions_get()
    if not positions:
        return

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
        pad_pts = SPREAD_PAD_POINTS.get(sym, 20)
        spread_pad = pad_pts * point

        # Estimate initial risk unit R (distance from entry to original SL or 1.5 ATR pad)
        if sl > 0 and abs(open_price - sl) > spread_pad:
            initial_risk = abs(open_price - sl)
        else:
            initial_risk = 250 * point

        # Compute continuous R-multiple gain
        gain = (mark - open_price) if is_buy else (open_price - mark)
        r_mult = gain / initial_risk if initial_risk > 0 else 0.0

        # === TIER 1: BREAKEVEN LOCK (+1.0R) ===
        if r_mult >= 1.0:
            target_be_sl = round(open_price + spread_pad if is_buy else open_price - spread_pad, digits)
            needs_be_lock = False
            if is_buy and (sl < target_be_sl or sl == 0.0):
                needs_be_lock = True
            elif not is_buy and (sl > target_be_sl or sl == 0.0):
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
                    print(f"[BE-LOCK] Ticket #{ticket} ({sym}) @ +{r_mult:.2f}R -> SL locked to {target_be_sl}")

        # === TIER 2: 50% PARTIAL PROFIT HARVEST (+1.8R) ===
        if r_mult >= 1.8 and ticket not in scaled_tickets:
            step = sym_info.volume_step
            min_lot = sym_info.volume_min
            half_vol = round(math.floor((volume / 2.0) / step) * step, 2)

            if half_vol >= min_lot and (volume - half_vol) >= min_lot:
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                close_price = sym_info.bid if is_buy else sym_info.ask
                close_filling = get_filling_mode(sym)

                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": ticket,
                    "symbol": sym,
                    "volume": half_vol,
                    "type": close_type,
                    "price": close_price,
                    "deviation": 25,
                    "magic": 999101,
                    "comment": "Nexus 1.8R Partial Scale",
                    "type_filling": close_filling
                }
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"[PARTIAL-SCALE] Ticket #{ticket} ({sym}) closed {half_vol}L @ +{r_mult:.2f}R")
                    scaled_tickets.add(ticket)
                    save_state()

                    # Trail runner SL to +0.8R
                    runner_sl = round(open_price + (0.8 * initial_risk) if is_buy else open_price - (0.8 * initial_risk), digits)
                    mod_req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": ticket,
                        "symbol": sym,
                        "sl": runner_sl,
                        "tp": p.tp
                    }
                    mt5.order_send(mod_req)

if __name__ == "__main__":
    print("[NEXUS-DEFENSE] Breakeven & Trailing Engine armed and monitoring.")
    while True:
        try:
            process_active_positions()
        except Exception as e:
            print(f"[!] Breakeven loop error: {e}")
        time.sleep(3)

