"""
NEXUS ALPHA DECAY // TEMPORAL HORIZON EXPIRATION & ZOMBIE POSITION REAPER
"""
import time
import json
import os
import requests
import MetaTrader5 as mt5
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
REGISTRY_FILE = "partial_tp_registry.json"

HALF_LIFE_SECONDS = 14400    # 4 Hours (Soft Risk Choke)
TERMINAL_HOLD_SECONDS = 28800 # 8 Hours (Hard Liquidation)

def send_decay_telegram(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass

def is_armored_runner(pos) -> bool:
    """Returns True if position is an armored runner (BE locked or banked 50%)."""
    # Check if banked in registry
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r") as f:
                banked = set(json.load(f).get("banked_tickets", []))
                if pos.ticket in banked:
                    return True
        except Exception:
            pass

    # Check if SL is at or beyond entry price
    is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
    if is_buy and pos.sl >= pos.price_open:
        return True
    if not is_buy and pos.sl > 0 and pos.sl <= pos.price_open:
        return True

    return False

def evaluate_alpha_decay_cycle(pos, atr: float):
    """
    Evaluates position age against alpha half-life decay thresholds.
    """
    if atr <= 0:
        return False

    # Never reap an armored winning runner
    if is_armored_runner(pos):
        return False

    now_ts = int(time.time())
    elapsed_seconds = now_ts - pos.time
    ticket = pos.ticket
    symbol = pos.symbol
    sym_info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not sym_info or not tick:
        return False

    is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
    current_price = tick.bid if is_buy else tick.ask
    open_price = pos.price_open
    price_gain = (current_price - open_price) if is_buy else (open_price - current_price)
    digits = sym_info.digits
    point = sym_info.point

    # Phase 2: Terminal Invalidation Reaping (Elapsed >= 8 Hours)
    if elapsed_seconds >= TERMINAL_HOLD_SECONDS:
        if price_gain < (1.0 * atr):
            opp_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
            close_req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": pos.volume,
                "type": opp_type,
                "position": ticket,
                "price": current_price,
                "deviation": 25,
                "magic": 999995,
                "comment": "THETA_REAP_8H",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(close_req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                hours_held = round(elapsed_seconds / 3600, 1)
                pnl_usd = round(pos.profit + pos.swap, 2)
                msg = (
                    f"⏳ <b>ALPHA HALF-LIFE EXPIRED // POSITION REAPED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• <b>Ticket</b>: <code>#{ticket}</code> ({symbol})\n"
                    f"• <b>Elapsed Time</b>: <code>{hours_held} Hours</code> (Threshold: 8h)\n"
                    f"• <b>Final PnL</b>: <code>${pnl_usd:+.2f}</code>\n"
                    f"• <b>Reason</b>: Momentum stagnation (Failed to reach 1.0x ATR)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔓 <i>Portfolio Slot Released for High-Velocity Alpha</i>"
                )
                send_decay_telegram(msg)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Reaped stagnant position #{ticket} {symbol} ({hours_held}h held)")
                return True

    # Phase 1: Soft Risk Choke (Elapsed >= 4 Hours)
    elif elapsed_seconds >= HALF_LIFE_SECONDS:
        if price_gain < (0.6 * atr):
            # Tighten SL to entry +- 0.75x ATR
            choked_sl = (open_price - (0.75 * atr)) if is_buy else (open_price + (0.75 * atr))
            should_choke = False

            if is_buy and (pos.sl < choked_sl):
                should_choke = True
            elif not is_buy and (pos.sl == 0 or pos.sl > choked_sl):
                should_choke = True

            if should_choke:
                mod_req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "symbol": symbol,
                    "sl": round(choked_sl, digits),
                    "tp": pos.tp,
                }
                res = mt5.order_send(mod_req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    hours_held = round(elapsed_seconds / 3600, 1)
                    msg = (
                        f"🛡️ <b>ALPHA DECAY // DEFENSIVE SL TIGHTENED</b>\n"
                        f"• <b>Ticket</b>: <code>#{ticket}</code> ({symbol})\n"
                        f"• <b>Elapsed Time</b>: <code>{hours_held} Hours</code> (Half-Life reached)\n"
                        f"• <b>New Defensive SL</b>: <code>{choked_sl:.{digits}f}</code> (-0.75x ATR)\n"
                        f"• <b>Action</b>: Capital risk throttled 50% due to momentum deceleration"
                    )
                    send_decay_telegram(msg)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛡️ Tightened defensive SL on #{ticket} {symbol} due to alpha half-life")
                    return True

    return False
