#!/usr/bin/env python3
"""
NEXUS OMEGA APEX FINAL PRODUCTION DAEMON (v44.2 Multi-Terminal)
- CLI Isolated: --terminal, --portable, --magic, --tag
- Strategy: Anchored Asian Box (00:00-03:45 UTC) + H1 EMA20/50 + PDH/PDL Clearance + M15 VPOC Anti-Chop
- Execution: Pre-Armed Coiled BUY_STOP / SELL_STOP at 04:00 UTC (with 13:15-13:45 UTC US News HMR Cancel/Re-Arm)
- Session Gates: US30 (13:46-16:00 UTC NY Cash Open), XAUUSD (07:00-16:00 UTC London/NY), FX/BTC (04:00-16:00 UTC)
- Risk & Harvest: 0.75% Risk/Trade, Max-1 USD FX Correlation Cap, -2.0% Daily Circuit Breaker, T1 (+0.85R BE), T2 (+1.60R 50% Harvest), EOD Flat (22:45 UTC)
"""

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import urllib.request

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
SYMBOLS = ["XAUUSD", "BTCUSD", "US30", "EURUSD", "USDCHF", "USDCAD"]
USD_CORR_BASES = {"EURUSD", "USDCHF", "USDCAD"}

RISK_PER_TRADE = 0.0075
MAX_DAILY_DD = 0.020
MAX_CONCURRENT_POS = 3
POLL_SECONDS = 60


def parse_args():
    p = argparse.ArgumentParser(description="Nexus Omega Apex Final Production Daemon")
    p.add_argument("--terminal", default=r"C:/MT5_Quant_278061453/terminal64.exe", help="Path to terminal64.exe")
    p.add_argument("--portable", action="store_true", help="Initialize MT5 in portable mode")
    p.add_argument("--magic", type=int, default=44044, help="Unique Magic Number for this terminal")
    p.add_argument("--tag", default="T1_QUANT", help="Instance tag for logs, state, and Telegram alerts")
    return p.parse_args()


def setup_logger(tag: str) -> logging.Logger:
    log_path = BASE_DIR / f"nexus_omega_apex_{tag}.log"
    logger = logging.getLogger(f"omega_{tag}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter(f"%(asctime)s [UTC] [{tag}] %(levelname)s: %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def send_telegram(tag: str, msg: str, log: logging.Logger):
    cfg_path = BASE_DIR / "t2_telegram_config.json"
    if not cfg_path.exists():
        return
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        token = cfg.get("bot_token") or cfg.get("token")
        chat_id = cfg.get("chat_id")
        if not token or not chat_id:
            return
        payload = json.dumps({"chat_id": chat_id, "text": f"[{tag}] {msg}"}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        log.warning("Telegram notify skipped: %s", exc)


def load_state(state_file: Path, today_str: str, current_eq: float) -> dict:
    if state_file.exists():
        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
            if st.get("date") == today_str:
                return st
        except Exception:
            pass
    st = {
        "date": today_str,
        "start_equity": current_eq,
        "halted": False,
        "traded_bases": [],
        "t1_done": [],
        "t2_done": [],
        "peaks": {},
    }
    save_state(state_file, st)
    return st


def save_state(state_file: Path, st: dict):
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    tmp.replace(state_file)


def ensure_mt5(terminal_path: str, portable: bool, log: logging.Logger) -> bool:
    ti = mt5.terminal_info()
    ai = mt5.account_info()
    if ti is not None and ai is not None and ti.connected:
        return True
    mt5.shutdown()
    if mt5.initialize(path=terminal_path, portable=portable, timeout=15000):
        ai = mt5.account_info()
        if ai is not None:
            log.info("Connected MT5 Account #%s | Balance=$%.2f | Equity=$%.2f", ai.login, ai.balance, ai.equity)
            return True
    log.error("MT5 initialize failed for %s (portable=%s): %s", terminal_path, portable, mt5.last_error())
    return False


def resolve_symbol(base: str) -> str | None:
    if mt5.symbol_info(base) is not None:
        mt5.symbol_select(base, True)
        return base
    for s in (mt5.symbols_get() or []):
        if s.name.startswith(base) and len(s.name) <= len(base) + 3 and s.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
            mt5.symbol_select(s.name, True)
            return s.name
    return None


def base_of_symbol(sym: str) -> str:
    for b in SYMBOLS:
        if sym.startswith(b):
            return b
    return sym


def in_session_window(base: str, hour: int, minute: int) -> bool:
    # Block US News HMR window (13:15-13:45 UTC) globally
    if hour == 13 and 15 <= minute <= 45:
        return False
    if base == "US30":
        return (hour == 13 and minute >= 46) or (14 <= hour <= 16)
    if base == "XAUUSD":
        return 7 <= hour <= 16
    return 4 <= hour <= 16


def compute_lot(sym: str, sl_dist: float, equity: float) -> float:
    info = mt5.symbol_info(sym)
    if info is None or sl_dist <= 0 or info.trade_tick_size <= 0 or info.trade_tick_value <= 0:
        return 0.0
    risk_usd = equity * RISK_PER_TRADE
    ticks = sl_dist / info.trade_tick_size
    loss_per_lot = ticks * info.trade_tick_value
    if loss_per_lot <= 0:
        return info.volume_min
    raw_lot = risk_usd / loss_per_lot
    step = info.volume_step if info.volume_step > 0 else 0.01
    lot = math.floor(raw_lot / step) * step
    lot = max(info.volume_min, min(info.volume_max, round(lot, 2)))
    return lot


def evaluate_symbol(base: str, sym: str, today_date) -> dict | None:
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if info is None or tick is None:
        return None

    r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 140)
    rd1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5)
    if r15 is None or rd1 is None or len(r15) < 60 or len(rd1) < 2:
        return None

    df = pd.DataFrame(r15)
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df["date"] = df["dt"].dt.date

    prev_c = df["close"].shift(1)
    tr = np.maximum(df["high"] - df["low"], np.maximum((df["high"] - prev_c).abs(), (df["low"] - prev_c).abs()))
    df["atr20"] = tr.rolling(20).mean().bfill()
    df["atr56"] = tr.rolling(56).mean().bfill()
    df["ema20"] = df["close"].ewm(span=80, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=200, adjust=False).mean()

    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["tick_volume"].astype(float)
    df["vol_ratio"] = vol / np.maximum(vol.rolling(20).mean(), 1.0)
    vpoc = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
    va_std = typical.rolling(16).std().fillna(df["atr20"])
    df["chop"] = (df["close"] - vpoc).abs() <= (0.20 * va_std)

    today_df = df[df["date"] == today_date]
    if len(today_df) < 16:
        return None

    ref = today_df.iloc[:16]  # 00:00-03:45 UTC Anchored Asian Box
    box_hi = float(ref["high"].max())
    box_lo = float(ref["low"].min())
    atr_b = float(ref["atr20"].iloc[-1])
    atr_56 = float(ref["atr56"].iloc[-1])
    box_rng = box_hi - box_lo
    max_mult = 3.4 if "XAU" in base else 2.6

    if not ((atr_b * 0.60) <= box_rng <= (atr_56 * max_mult)):
        return None

    buf = atr_b * 0.40
    sl_dist = atr_b * 1.25
    buy_stop = round(box_hi + buf, info.digits)
    sell_stop = round(box_lo - buf, info.digits)

    pdh = float(rd1[-2]["high"])
    pdl = float(rd1[-2]["low"])
    pdh_clear = (pdh <= buy_stop) or ((pdh - buy_stop) >= sl_dist * 0.90)
    pdl_clear = (pdl >= sell_stop) or ((sell_stop - pdl) >= sl_dist * 0.90)

    prev = df.iloc[-2]
    if bool(prev["chop"]):
        return None

    bull = (prev["close"] > prev["ema20"]) and (prev["ema20"] > prev["ema50"]) and pdh_clear
    bear = (prev["close"] < prev["ema20"]) and (prev["ema20"] < prev["ema50"]) and pdl_clear
    if not (bull or bear):
        return None

    direction = "BUY" if bull else "SELL"
    if direction == "BUY" and tick.ask >= buy_stop:
        return None
    if direction == "SELL" and tick.bid <= sell_stop:
        return None

    edge_score = round(float(prev["vol_ratio"]) * 50.0 + (15.0 if (bull and pdh <= buy_stop) or (bear and pdl >= sell_stop) else 5.0), 1)
    return {
        "base": base,
        "symbol": sym,
        "direction": direction,
        "buy_stop": buy_stop,
        "sell_stop": sell_stop,
        "sl_dist": sl_dist,
        "vol_ratio": float(prev["vol_ratio"]),
        "edge_score": edge_score,
    }


def manage_open_positions(magic: int, tag: str, st: dict, state_file: Path, now_utc: datetime, log: logging.Logger):
    positions = [p for p in (mt5.positions_get() or []) if p.magic == magic]
    eod_flat = (now_utc.hour > 22) or (now_utc.hour == 22 and now_utc.minute >= 45)

    for p in positions:
        sym = p.symbol
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            continue

        if eod_flat:
            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            px = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": sym,
                "volume": p.volume,
                "type": close_type,
                "position": p.ticket,
                "price": px,
                "deviation": 30,
                "magic": magic,
                "comment": f"{tag}_EOD_EXIT",
            })
            log.info("[EOD FLAT] Closed #%s %s %.2fL @ %s", p.ticket, sym, p.volume, px)
            continue

        sl_dist = abs(p.price_open - p.sl) if p.sl > 0 else 0.0
        if sl_dist <= 0:
            continue

        t_key = str(p.ticket)
        is_buy = (p.type == mt5.POSITION_TYPE_BUY)
        cur_px = tick.bid if is_buy else tick.ask
        gain = (cur_px - p.price_open) if is_buy else (p.price_open - cur_px)
        prev_peak = float(st["peaks"].get(t_key, 0.0))
        peak = max(prev_peak, gain)
        st["peaks"][t_key] = peak

        # T1 (+0.85R -> Move SL to BE + 0.12R)
        if t_key not in st["t1_done"] and gain >= sl_dist * 0.85:
            lock_be = round(p.price_open + sl_dist * 0.12, info.digits) if is_buy else round(p.price_open - sl_dist * 0.12, info.digits)
            if (is_buy and lock_be > p.sl) or ((not is_buy) and lock_be < p.sl):
                res = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": sym, "position": p.ticket, "sl": lock_be, "tp": p.tp})
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    st["t1_done"].append(t_key)
                    log.info("[T1 BE LOCK] #%s %s SL -> %s (+0.12R)", p.ticket, sym, lock_be)

        # T2 (+1.60R -> 50% Partial Harvest + Lock SL at +1.05R)
        if t_key not in st["t2_done"] and gain >= sl_dist * 1.60:
            step = info.volume_step if info.volume_step > 0 else 0.01
            half_vol = math.floor((p.volume * 0.50) / step) * step
            if half_vol >= info.volume_min and (p.volume - half_vol) >= info.volume_min:
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                px = tick.bid if is_buy else tick.ask
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": sym,
                    "volume": round(half_vol, 2),
                    "type": close_type,
                    "position": p.ticket,
                    "price": px,
                    "deviation": 30,
                    "magic": magic,
                    "comment": f"{tag}_T2_HARVEST",
                })
            lock_t2 = round(p.price_open + sl_dist * 1.05, info.digits) if is_buy else round(p.price_open - sl_dist * 1.05, info.digits)
            if (is_buy and lock_t2 > p.sl) or ((not is_buy) and lock_t2 < p.sl):
                mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": sym, "position": p.ticket, "sl": lock_t2, "tp": p.tp})
            st["t2_done"].append(t_key)
            log.info("[T2 HARVEST] #%s %s 50%% harvested & SL locked -> %s (+1.05R)", p.ticket, sym, lock_t2)
            send_telegram(tag, f"T2 HARVEST {sym} #{p.ticket} @ {cur_px} | SL locked +1.05R", log)

        # Runner Trail (>= +2.20R -> Trail at 65% of peak excursion)
        if t_key in st["t2_done"] and peak >= sl_dist * 2.20:
            trail_sl = round(p.price_open + peak * 0.65, info.digits) if is_buy else round(p.price_open - peak * 0.65, info.digits)
            if (is_buy and trail_sl > p.sl) or ((not is_buy) and trail_sl < p.sl):
                mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": sym, "position": p.ticket, "sl": trail_sl, "tp": p.tp})

    save_state(state_file, st)


def main():
    args = parse_args()
    log = setup_logger(args.tag)
    state_file = BASE_DIR / f"state_{args.tag}_{args.magic}.json"
    log.info("STARTING OMEGA APEX FINAL PRODUCTION | Terminal=%s | Portable=%s | Magic=%s", args.terminal, args.portable, args.magic)

    while True:
        try:
            if not ensure_mt5(args.terminal, args.portable, log):
                time.sleep(POLL_SECONDS)
                continue

            now_utc = datetime.now(timezone.utc)
            today_date = now_utc.date()
            today_str = today_date.isoformat()
            ai = mt5.account_info()
            ti = mt5.terminal_info()
            if ai is None or ti is None:
                time.sleep(POLL_SECONDS)
                continue

            st = load_state(state_file, today_str, float(ai.equity))

            # Daily -2.0% Equity Circuit Breaker
            dd_pct = (st["start_equity"] - float(ai.equity)) / max(st["start_equity"], 1.0)
            if dd_pct >= MAX_DAILY_DD and not st["halted"]:
                st["halted"] = True
                save_state(state_file, st)
                log.warning("[CIRCUIT BREAKER] Daily DD %.2f%% >= 2.0%%. Halting new entries today.", dd_pct * 100.0)
                send_telegram(args.tag, f"CIRCUIT BREAKER HALT: Daily DD {dd_pct*100:.2f}%", log)

            # Manage existing positions first
            manage_open_positions(args.magic, args.tag, st, state_file, now_utc, log)

            my_pos = [p for p in (mt5.positions_get() or []) if p.magic == args.magic]
            my_ord = [o for o in (mt5.orders_get() or []) if o.magic == args.magic]

            # Record any filled positions as traded today
            for p in my_pos:
                b = base_of_symbol(p.symbol)
                if b not in st["traded_bases"]:
                    st["traded_bases"].append(b)
                    save_state(state_file, st)

            # Cancel unarmed pending stop orders outside valid session windows (e.g., 13:15-13:45 HMR or >16:00 UTC)
            for o in list(my_ord):
                b = base_of_symbol(o.symbol)
                if st["halted"] or not ti.trade_allowed or not in_session_window(b, now_utc.hour, now_utc.minute):
                    mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                    log.info("[ORDER CANCEL] Removed unarmed pending #%s (%s) outside active window.", o.ticket, o.symbol)

            # Refresh pending orders list
            my_ord = [o for o in (mt5.orders_get() or []) if o.magic == args.magic]
            active_bases = {base_of_symbol(p.symbol) for p in my_pos} | {base_of_symbol(o.symbol) for o in my_ord} | set(st["traded_bases"])
            usd_used = any(b in USD_CORR_BASES for b in active_bases)

            # Pre-Arm Coiled BUY_STOP / SELL_STOP orders starting at 04:00 UTC
            if not st["halted"] and ti.trade_allowed and now_utc.hour >= 4 and (len(my_pos) + len(my_ord)) < MAX_CONCURRENT_POS:
                candidates = []
                for base in SYMBOLS:
                    if base in active_bases:
                        continue
                    if base in USD_CORR_BASES and usd_used:
                        continue
                    if not in_session_window(base, now_utc.hour, now_utc.minute):
                        continue
                    sym = resolve_symbol(base)
                    if not sym:
                        continue
                    cand = evaluate_symbol(base, sym, today_date)
                    if cand is not None:
                        candidates.append(cand)

                candidates.sort(key=lambda x: -x["edge_score"])
                for cand in candidates:
                    if (len(my_pos) + len(my_ord)) >= MAX_CONCURRENT_POS:
                        break
                    if cand["base"] in USD_CORR_BASES and usd_used:
                        continue

                    sym = cand["symbol"]
                    info = mt5.symbol_info(sym)
                    lot = compute_lot(sym, cand["sl_dist"], float(ai.equity))
                    if info is None or lot <= 0:
                        continue

                    if cand["direction"] == "BUY":
                        price = cand["buy_stop"]
                        sl = round(price - cand["sl_dist"], info.digits)
                        otype = mt5.ORDER_TYPE_BUY_STOP
                    else:
                        price = cand["sell_stop"]
                        sl = round(price + cand["sl_dist"], info.digits)
                        otype = mt5.ORDER_TYPE_SELL_STOP

                    req = {
                        "action": mt5.TRADE_ACTION_PENDING,
                        "symbol": sym,
                        "volume": lot,
                        "type": otype,
                        "price": price,
                        "sl": sl,
                        "deviation": 20,
                        "magic": args.magic,
                        "comment": f"{args.tag}_{cand['direction']}",
                        "type_time": mt5.ORDER_TIME_DAY,
                        "type_filling": mt5.ORDER_FILLING_RETURN,
                    }
                    res = mt5.order_send(req)
                    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                        my_ord.append(res)
                        active_bases.add(cand["base"])
                        if cand["base"] in USD_CORR_BASES:
                            usd_used = True
                        log.info(
                            "[PRE-ARMED %s_STOP] %s (Score=%.1f) %.2fL @ %s | SL=%s | Vol=%.2fx (#%s)",
                            cand["direction"], sym, cand["edge_score"], lot, price, sl, cand["vol_ratio"], res.order
                        )
                        send_telegram(args.tag, f"PRE-ARMED {cand['direction']}_STOP {sym} {lot:.2f}L @ {price} | SL={sl}", log)
                    else:
                        log.warning("[ORDER REJECTED] %s %s_STOP @ %s -> %s", sym, cand["direction"], price, res)

        except Exception as exc:
            log.exception("Loop exception: %s", exc)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
