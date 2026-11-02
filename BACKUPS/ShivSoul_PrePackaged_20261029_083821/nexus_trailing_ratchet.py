from nexus_alpha_decay import evaluate_alpha_decay_cycle
from nexus_profit_harvester import evaluate_and_harvest_position
﻿"""
NEXUS TRAILING RATCHET // AUTONOMOUS CHANDELIER ATR RUNNER ARMOR
"""
import os
import sys
import time
import asyncio
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_silent_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_notification": True
    }
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception:
        pass

def calculate_m15_atr(symbol: str, period: int = 14) -> float:
    import MetaTrader5 as mt5
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, period + 15)
    if rates is None or len(rates) < period + 1:
        return 0.0
    df = pd.DataFrame(rates)
    highs = df['high'].to_numpy()
    lows = df['low'].to_numpy()
    closes = df['close'].to_numpy()
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
    return float(np.mean(tr[-period:]))

def run_ratchet_cycle():
    """Single execution cycle of the autonomous ATR Chandelier Ratchet."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return

    positions = mt5.positions_get()
    if not positions:
        return

    for p in positions:
        symbol = p.symbol
        ticket = p.ticket
        sym_info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if not sym_info or not tick:
            continue

        digits = sym_info.digits
        point = sym_info.point
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        current_price = tick.bid if is_buy else tick.ask
        open_price = p.price_open
        current_sl = p.sl

        # Calculate floating profit distance in price
        price_gain = (current_price - open_price) if is_buy else (open_price - current_price)
        if price_gain <= 0:
            continue

        atr = calculate_m15_atr(symbol, 14)
        if atr <= 0:
            continue

        # Autonomous TP1 Scale-Out (50% Cash Banked at +1.2x ATR)
        harvested = evaluate_and_harvest_position(p, atr)

        # Alpha Half-Life Temporal Invalidation & Theta Reaper
        decay_acted = evaluate_alpha_decay_cycle(p, atr)
        if decay_acted:
            continue

        be_buffer = 20 * point  # 2 pips
        be_target_sl = (open_price + be_buffer) if is_buy else (open_price - be_buffer)

        # -------------------------------------------------------------
        # Phase 1: Zero-Touch Auto-Armor (Floating Gain >= 1.0x ATR)
        # -------------------------------------------------------------
        needs_be_lock = False
        if is_buy and (current_sl < be_target_sl):
            needs_be_lock = (price_gain >= 1.0 * atr)
        elif not is_buy and (current_sl == 0 or current_sl > be_target_sl):
            needs_be_lock = (price_gain >= 1.0 * atr)

        if needs_be_lock:
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": symbol,
                "sl": round(be_target_sl, digits),
                "tp": p.tp,
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                send_silent_telegram(
                    f"🛡️ <b>ARMOR AUTO-LOCKED // BE +2 PIPS</b>\n"
                    f"• <b>Ticket</b>: <code>#{ticket}</code> ({symbol})\n"
                    f"• <b>Entry</b>: <code>{open_price:.{digits}f}</code>\n"
                    f"• <b>SL Secured</b>: <code>{be_target_sl:.{digits}f}</code>\n"
                    f"• <b>Trigger</b>: Floating Gain crossed 1.0x ATR"
                )
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛡️ Auto-Locked BE on #{ticket} {symbol}")
                continue

        # -------------------------------------------------------------
        # Phase 2: Chandelier Trailing Ratchet (Floating Gain >= 1.5x ATR)
        # -------------------------------------------------------------
        if price_gain >= 1.5 * atr:
            proposed_sl = (current_price - (1.0 * atr)) if is_buy else (current_price + (1.0 * atr))
            
            # Require minimum 0.25x ATR bump to prevent micro-step thrashing
            min_step = 0.25 * atr
            should_ratchet = False

            if is_buy and (proposed_sl > current_sl + min_step) and (proposed_sl > be_target_sl):
                should_ratchet = True
            elif not is_buy and (current_sl > 0) and (proposed_sl < current_sl - min_step) and (proposed_sl < be_target_sl):
                should_ratchet = True

            if should_ratchet:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "symbol": symbol,
                    "sl": round(proposed_sl, digits),
                    "tp": p.tp,
                }
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    locked_gain = (proposed_sl - open_price) if is_buy else (open_price - proposed_sl)
                    locked_pct = (locked_gain / open_price) * 100.0
                    send_silent_telegram(
                        f"📈 <b>CHANDELIER RATCHET // SL ADVANCED</b>\n"
                        f"• <b>Ticket</b>: <code>#{ticket}</code> ({symbol})\n"
                        f"• <b>New Trailing SL</b>: <code>{proposed_sl:.{digits}f}</code>\n"
                        f"• <b>Guaranteed Profit</b>: <code>+{locked_pct:.2f}%</code>\n"
                        f"• <b>Trail Buffer</b>: 1.0x ATR ({atr:.{digits}f})"
                    )
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 Ratchet Advanced #{ticket} {symbol} SL -> {proposed_sl:.{digits}f}")

async def autonomous_trailing_ratchet():
    """Continuous background worker running every 5 seconds."""
    print("[*] Autonomous Chandelier ATR Ratchet Engine Online (5s cycle).")
    while True:
        try:
            run_ratchet_cycle()
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[!] Ratchet loop exception: {e}")
            await asyncio.sleep(10)
