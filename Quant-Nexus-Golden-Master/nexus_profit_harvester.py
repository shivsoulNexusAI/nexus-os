from nexus_vol_regime_engine import evaluate_volatility_regime
"""
NEXUS PROFIT HARVESTER // AUTONOMOUS ASYMMETRIC SCALE-OUT & RUNNER UNLEASHING
"""
import os
import json
import MetaTrader5 as mt5
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
REGISTRY_FILE = "partial_tp_registry.json"

def send_harvester_telegram(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass

def load_harvest_registry() -> set:
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("banked_tickets", []))
        except Exception:
            pass
    return set()

def record_harvested_ticket(ticket: int):
    banked = load_harvest_registry()
    banked.add(ticket)
    try:
        with open(REGISTRY_FILE, "w") as f:
            json.dump({"banked_tickets": list(banked)}, f, indent=2)
    except Exception:
        pass

def evaluate_and_harvest_position(pos, atr: float):
    """
    Evaluates an open MT5 position for autonomous TP1 (+1.2x ATR) 50% scale-out.
    """
    if atr <= 0:
        return False

    ticket = pos.ticket
    banked_tickets = load_harvest_registry()
    if ticket in banked_tickets:
        return False  # Already harvested 50%

    symbol = pos.symbol
    sym_info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not sym_info or not tick:
        return False

    is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
    current_price = tick.bid if is_buy else tick.ask
    open_price = pos.price_open
    price_gain = (current_price - open_price) if is_buy else (open_price - current_price)

    # TP1 Threshold: 1.2x ATR Expansion
    tp1_target_gain = 1.2 * atr
    if price_gain < tp1_target_gain:
        return False

    # Execute 50% partial market closure
    vol_step = sym_info.volume_step if sym_info.volume_step else 0.01
    close_vol = round(round(pos.volume * 0.5 / vol_step) * vol_step, 2)
    min_vol = sym_info.volume_min if sym_info.volume_min else 0.01

    if close_vol < min_vol:
        return False

    opp_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    close_req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": close_vol,
        "type": opp_type,
        "position": ticket,
        "price": current_price,
        "deviation": 25,
        "magic": 777903,
        "comment": f"AutoTP1 #{ticket}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    res_close = mt5.order_send(close_req)
    if not res_close or res_close.retcode != mt5.TRADE_RETCODE_DONE:
        return False

    record_harvested_ticket(ticket)

    # Snap Stop Loss to Break-Even + 2 pips and clear static TP ceiling
    digits = sym_info.digits
    point = sym_info.point
    be_price = (open_price + (20 * point)) if is_buy else (open_price - (20 * point))

    modify_req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": symbol,
        "sl": round(be_price, digits),
        "tp": 0.0,  # Remove hard TP ceiling: let runner ride on Chandelier Ratchet
    }
    mt5.order_send(modify_req)

    gain_usd = close_vol * (price_gain / point) * sym_info.trade_tick_value if point > 0 else 0.0
    msg = (
        f"💰 <b>AUTONOMOUS TP1 HARVESTED // 50% CASH BANKED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Ticket</b>: <code>#{ticket}</code> ({symbol})\n"
        f"• <b>Banked Volume</b>: <code>{close_vol} Lots</code>\n"
        f"• <b>Execution Price</b>: <code>{current_price:.{digits}f}</code>\n"
        f"• <b>Trigger</b>: Reached +1.2x ATR ({tp1_target_gain:.{digits}f})\n"
        f"• <b>Stop Loss Status</b>: <code>Armored at BE + 2 pips</code>\n"
        f"• <b>Target Ceiling</b>: <code>REMOVED (Uncapped Runner Active)</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Position is now a Risk-Free Synthetic Free Option</i>"
    )
    send_harvester_telegram(msg)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 Auto-Harvested 50% on #{ticket} {symbol} @ {current_price:.{digits}f}")
    return True
