"""
QUANT-NEXUS TERMINAL 4 (T4) // VERIFIED 11/04/2026 SOVEREIGN NEXUS REPLICA (#278060961)
Exact Forensic Parity Build:
- SCAN_SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "GBPUSD"]
- 60-Second Multi-Asset Confluence Sweep (TIMEFRAME_M15, 100 bars, EMA 9/21/50 + RSI14 + 10-bar Breakout >= 80.0)
- Exact Calibrated Router Offsets (sl_offset / tp1_offset) + 1.0% Equity-Parity Risk Sizing
- Exact Deal Fingerprint from #278060961 History: magic=999888, comment="Nexus Autonomous"
- 4-Stage Autonomous Lifecycle: 1.0x M15 ATR BE (+2 pips) -> 1.2x ATR 50% Harvest -> 1.5x ATR Chandelier -> 4h/8h Decay
"""
import os
import sys
import json
import time
import sqlite3
import logging
from datetime import datetime, timezone
import numpy as np
import MetaTrader5 as mt5

T4_MT5_PATH = r"C:\MT5_Sovereign_T4\terminal64.exe"
LEDGER_DB = r"C:\Quant-Nexus-Eng\nexus_ledger.db"
STATE_FILE = r"C:\Quant-Nexus-Eng\t4_sovereign_state.json"
LOG_FILE = r"C:\Quant-Nexus-Eng\logs\t4_sovereign_apex.log"

SCAN_SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "GBPUSD"]
CONFLUENCE_GATE = 80.0
RISK_PCT = 0.01
SCAN_INTERVAL_SEC = 60.0
MAGIC_SOVEREIGN = 999888
ORDER_COMMENT = "Nexus Autonomous"
HALF_LIFE_SEC = 14400     # 4 Hours
TERMINAL_SEC = 28800      # 8 Hours

ROUTER_PROFILES = {
    "BTC": {"canonical": "BTCUSD", "name": "Bitcoin / U.S. Dollar", "digits": 2, "sl_offset": 280.0, "tp1_offset": 450.0, "tp2_offset": 950.0},
    "ETH": {"canonical": "ETHUSD", "name": "Ethereum / U.S. Dollar", "digits": 2, "sl_offset": 18.0, "tp1_offset": 32.0, "tp2_offset": 65.0},
    "XAU": {"canonical": "XAUUSD", "name": "Gold Spot / U.S. Dollar", "digits": 2, "sl_offset": 3.80, "tp1_offset": 6.50, "tp2_offset": 12.00},
    "EUR": {"canonical": "EURUSD", "name": "Euro / U.S. Dollar", "digits": 5, "sl_offset": 0.00180, "tp1_offset": 0.00320, "tp2_offset": 0.00650},
    "GBP": {"canonical": "GBPUSD", "name": "British Pound / U.S. Dollar", "digits": 5, "sl_offset": 0.00220, "tp1_offset": 0.00380, "tp2_offset": 0.00750},
}

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [T4-SOVEREIGN-1104] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("T4_Sovereign_1104")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"banked_tickets": [], "choked_tickets": []}


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log.warning(f"State save failed: {e}")


def get_exact_broker_symbol(base_sym: str) -> str:
    candidates = [base_sym, f"{base_sym}m", f"{base_sym}.s", f"{base_sym}c", f"{base_sym}raw", f"{base_sym}.a", f"{base_sym}_i"]
    for s in candidates:
        info = mt5.symbol_info(s)
        if info is not None and not s.endswith("_x10"):
            mt5.symbol_select(s, True)
            return s
    return base_sym


def is_market_open(symbol: str) -> bool:
    real_sym = get_exact_broker_symbol(symbol)
    tick = mt5.symbol_info_tick(real_sym)
    if not tick or tick.bid <= 0:
        return False
    if (time.time() - tick.time) > 86400:
        return False
    info = mt5.symbol_info(real_sym)
    return bool(info and info.trade_mode in [mt5.SYMBOL_TRADE_EXECUTION_MARKET, mt5.SYMBOL_TRADE_MODE_FULL])


def resolve_router(base_asset: str, real_sym: str) -> dict:
    key = "BTC"
    for k in ("BTC", "ETH", "XAU", "EUR", "GBP"):
        if k in base_asset.upper():
            key = k
            break
    prof = dict(ROUTER_PROFILES[key])
    prof["base"] = key
    prof["symbol"] = real_sym
    info = mt5.symbol_info(real_sym)
    if info:
        prof["digits"] = info.digits
    return prof


def calc_ema(arr: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1.0)
    out = [float(arr[0])]
    for p in arr[1:]:
        out.append(alpha * float(p) + (1.0 - alpha) * out[-1])
    return np.array(out, dtype=float)


def calculate_confluence_edge(symbol: str) -> dict:
    """Exact 11/04/2026 sovereign_nexus.py TIMEFRAME_M15 100-bar Confluence Engine."""
    real_sym = get_exact_broker_symbol(symbol)
    tick = mt5.symbol_info_tick(real_sym)
    spot_fallback = float(tick.bid) if tick else 0.0
    fallback_data = {"score": 50.0, "bias": "NEUTRAL", "rsi": 50.0, "spot": spot_fallback, "status": "CONSOLIDATION"}

    rates = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None or len(rates) < 50:
        return fallback_data

    try:
        closes = np.array([r["close"] for r in rates], dtype=float)
        highs = np.array([r["high"] for r in rates], dtype=float)
        lows = np.array([r["low"] for r in rates], dtype=float)

        ema9 = calc_ema(closes, 9)
        ema21 = calc_ema(closes, 21)
        ema50 = calc_ema(closes, 50)
        curr_c = float(closes[-1])

        deltas = np.diff(closes[-15:])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_g = float(np.mean(gains)) if len(gains) > 0 else 0.0
        avg_l = float(np.mean(losses)) if len(losses) > 0 else 0.0001
        rs = avg_g / (avg_l if avg_l != 0 else 0.0001)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        bull_pts = 0.0
        bear_pts = 0.0

        if ema9[-1] > ema21[-1] > ema50[-1]:
            bull_pts += 30.0
        elif ema9[-1] < ema21[-1] < ema50[-1]:
            bear_pts += 30.0
        elif ema9[-1] > ema21[-1]:
            bull_pts += 15.0
        elif ema9[-1] < ema21[-1]:
            bear_pts += 15.0

        if rsi < 32.0:
            bull_pts += 35.0
        elif rsi > 68.0:
            bear_pts += 35.0
        elif 40.0 <= rsi <= 55.0 and bull_pts > 0:
            bull_pts += 20.0
        elif 45.0 <= rsi <= 60.0 and bear_pts > 0:
            bear_pts += 20.0

        if curr_c > float(np.max(highs[-10:-1])):
            bull_pts += 25.0
        elif curr_c < float(np.min(lows[-10:-1])):
            bear_pts += 25.0

        if bull_pts > bear_pts:
            final_score = min(96.5, round(50.0 + (bull_pts * 0.48), 1))
            bias = "BUY" if final_score >= 65.0 else "NEUTRAL"
        elif bear_pts > bull_pts:
            final_score = min(96.5, round(50.0 + (bear_pts * 0.48), 1))
            bias = "SELL" if final_score >= 65.0 else "NEUTRAL"
        else:
            final_score = 50.0
            bias = "NEUTRAL"

        spot = float(tick.ask) if (tick and bias == "BUY") else (float(tick.bid) if tick else curr_c)
        return {
            "score": final_score,
            "bias": bias,
            "rsi": round(rsi, 1),
            "spot": spot,
            "status": "ACTIVE" if final_score >= CONFLUENCE_GATE else "SCANNING",
        }
    except Exception:
        return fallback_data


def calculate_dynamic_risk_lot(equity: float, symbol: str, entry: float, sl: float, risk_pct: float = 0.01) -> dict:
    info = mt5.symbol_info(symbol)
    sl_dist = abs(entry - sl)
    if not info or sl_dist <= 0 or info.trade_tick_size <= 0:
        return {"lot": 0.01, "risk_usd": round(equity * risk_pct, 2)}
    risk_cash = equity * risk_pct
    ticks_at_risk = sl_dist / info.trade_tick_size
    cash_per_lot = ticks_at_risk * info.trade_tick_value
    if cash_per_lot <= 0:
        return {"lot": info.volume_min, "risk_usd": round(risk_cash, 2)}
    raw_lot = risk_cash / cash_per_lot
    step = info.volume_step or 0.01
    steps = round(raw_lot / step)
    norm_lot = max(info.volume_min, min(info.volume_max, steps * step))
    step_str = str(step)
    vol_digits = len(step_str.split(".")[1]) if "." in step_str else 0
    return {"lot": round(norm_lot, vol_digits), "risk_usd": round(risk_cash, 2)}


def get_filling_mode(info) -> int:
    if info.filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    if info.filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def compute_m15_atr(symbol: str, period: int = 14) -> float:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, period + 15)
    if rates is None or len(rates) < period + 1:
        return 0.0
    highs = rates["high"]
    lows = rates["low"]
    closes = rates["close"]
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    return float(np.mean(tr[-period:]))


def update_heartbeat(login: int, equity: float, open_cnt: int, status: str):
    if not os.path.exists(LEDGER_DB):
        return
    try:
        conn = sqlite3.connect(LEDGER_DB, timeout=5.0)
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO worker_heartbeats (sleeve, pid, login, equity, open_count, last_tick_utc, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sleeve) DO UPDATE SET
                pid=excluded.pid, login=excluded.login, equity=excluded.equity,
                open_count=excluded.open_count, last_tick_utc=excluded.last_tick_utc, status=excluded.status
            """,
            ("T4", os.getpid(), int(login), float(equity), int(open_cnt), now_iso, status),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def manage_t4_positions(positions, state: dict):
    """Exact Sovereign Sentry: 1.0x M15 ATR BE+2pips -> 1.2x ATR 50% Bank -> 1.5x ATR Chandelier -> 4h/8h Decay."""
    now_ts = int(time.time())
    banked = set(state.get("banked_tickets", []))
    choked = set(state.get("choked_tickets", []))
    dirty = False

    for p in positions:
        sym = p.symbol
        ticket = p.ticket
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if not info or not tick:
            continue

        atr = compute_m15_atr(sym, 14)
        if atr <= 0:
            continue

        digits = info.digits
        point = info.point
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        curr_px = tick.bid if is_buy else tick.ask
        entry = p.price_open
        gain = (curr_px - entry) if is_buy else (entry - curr_px)
        be_sl = round((entry + 20 * point) if is_buy else (entry - 20 * point), digits)
        is_armored = (ticket in banked) or (is_buy and p.sl >= entry) or (not is_buy and 0 < p.sl <= entry)

        elapsed = now_ts - int(p.time)
        if not is_armored:
            if elapsed >= TERMINAL_SEC and gain < (1.0 * atr):
                opp = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": p.volume,
                    "type": opp, "position": ticket, "price": curr_px, "deviation": 25,
                    "magic": MAGIC_SOVEREIGN, "comment": "THETA_REAP_8H",
                    "type_time": mt5.ORDER_TIME_GTC, "type_filling": get_filling_mode(info),
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log.info(f"[THETA REAP 8H] Closed stagnant #{ticket} {sym} after {elapsed/3600:.1f}h")
                continue

            if elapsed >= HALF_LIFE_SEC and gain < (0.6 * atr) and ticket not in choked:
                new_sl = round((entry - 0.75 * atr) if is_buy else (entry + 0.75 * atr), digits)
                if (is_buy and p.sl < new_sl) or (not is_buy and (p.sl == 0 or p.sl > new_sl)):
                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP, "position": ticket,
                        "symbol": sym, "sl": new_sl, "tp": p.tp,
                    })
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        choked.add(ticket)
                        dirty = True
                        log.info(f"[ALPHA DECAY 4H] Tightened SL on #{ticket} {sym} -> {new_sl}")

        if gain <= 0:
            continue

        if gain >= (1.2 * atr) and ticket not in banked:
            step = info.volume_step or 0.01
            half_vol = round(round((p.volume * 0.5) / step) * step, 2)
            if half_vol >= info.volume_min and (p.volume - half_vol) >= info.volume_min:
                opp = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": half_vol,
                    "type": opp, "position": ticket, "price": curr_px, "deviation": 25,
                    "magic": MAGIC_SOVEREIGN, "comment": f"AutoTP1 #{ticket}",
                    "type_time": mt5.ORDER_TIME_GTC, "type_filling": get_filling_mode(info),
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    banked.add(ticket)
                    dirty = True
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP, "position": ticket,
                        "symbol": sym, "sl": be_sl, "tp": 0.0,
                    })
                    log.info(f"[TP1 50% BANKED] #{ticket} {sym}: Closed {half_vol}L | Runner SL={be_sl} (TP uncapped)")
                    continue

        if gain >= (1.0 * atr):
            if (is_buy and p.sl < be_sl) or (not is_buy and (p.sl == 0 or p.sl > be_sl)):
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP, "position": ticket,
                    "symbol": sym, "sl": be_sl, "tp": p.tp,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log.info(f"[AUTO-ARMOR BE+2p] #{ticket} {sym} SL locked @ {be_sl}")
                    continue

        if gain >= (1.5 * atr):
            prop_sl = round((curr_px - 1.0 * atr) if is_buy else (curr_px + 1.0 * atr), digits)
            min_step = 0.25 * atr
            if (is_buy and prop_sl > p.sl + min_step and prop_sl > be_sl) or (
                not is_buy and p.sl > 0 and prop_sl < p.sl - min_step and prop_sl < be_sl
            ):
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP, "position": ticket,
                    "symbol": sym, "sl": prop_sl, "tp": p.tp,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log.info(f"[CHANDELIER TRAIL] #{ticket} {sym} SL -> {prop_sl}")

    if dirty:
        state["banked_tickets"] = list(banked)[-200:]
        state["choked_tickets"] = list(choked)[-200:]
        save_state(state)


def run_t4_sovereign():
    if not mt5.initialize(path=T4_MT5_PATH, login=278071462, password=r"H@ngkook3695", server="Exness-MT5Trial5", portable=True):
        log.error(f"MT5 T4 init/login failed: {mt5.last_error()}")
        return
    acct_chk = mt5.account_info()
    if not acct_chk or acct_chk.login != 278071462:
        mt5.login(278071462, password=r"H@ngkook3695", server="Exness-MT5Trial5")

    acct = mt5.account_info()
    log.info(
        f"T4 SOVEREIGN NEXUS (11/04/2026 EXACT REPLICA) ONLINE | Account=#{acct.login} | "
        f"Equity=${acct.equity:.2f} | SCAN_SYMBOLS={SCAN_SYMBOLS} | Magic={MAGIC_SOVEREIGN} | Cycle=60s"
    )
    state = load_state()
    last_scan_ts = 0.0

    while True:
        try:
            acct = mt5.account_info()
            if not acct:
                time.sleep(3)
                continue

            positions = list(mt5.positions_get() or [])
            manage_t4_positions(positions, state)

            positions = list(mt5.positions_get() or [])
            status_str = f"MANAGING_ACTIVE({len(positions)})" if positions else "ACTIVE_SOVEREIGN(Open:0)"
            update_heartbeat(acct.login, acct.equity, len(positions), status_str)

            now_ts = time.time()
            if (now_ts - last_scan_ts) >= SCAN_INTERVAL_SEC:
                last_scan_ts = now_ts
                for asset in SCAN_SYMBOLS:
                    real_sym = get_exact_broker_symbol(asset)
                    if not is_market_open(real_sym):
                        continue
                    router = resolve_router(asset, real_sym)
                    base = router["base"]
                    if any(base in p.symbol.upper() for p in positions):
                        continue

                    data = calculate_confluence_edge(real_sym)
                    score = data.get("score", 0.0)
                    bias = data.get("bias", "NEUTRAL")
                    spot = data.get("spot", 0.0)
                    d = router["digits"]

                    if score >= CONFLUENCE_GATE and bias in ("BUY", "SELL") and spot > 0:
                        sl = round(spot - router["sl_offset"], d) if bias == "BUY" else round(spot + router["sl_offset"], d)
                        tp = round(spot + router["tp1_offset"], d) if bias == "BUY" else round(spot - router["tp1_offset"], d)
                        calc = calculate_dynamic_risk_lot(float(acct.equity), real_sym, spot, sl, RISK_PCT)
                        info = mt5.symbol_info(real_sym)
                        if not info:
                            continue

                        req = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": real_sym,
                            "volume": calc["lot"],
                            "type": mt5.ORDER_TYPE_BUY if bias == "BUY" else mt5.ORDER_TYPE_SELL,
                            "price": spot,
                            "sl": sl,
                            "tp": tp,
                            "deviation": 30,
                            "magic": MAGIC_SOVEREIGN,
                            "comment": ORDER_COMMENT,
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": get_filling_mode(info),
                        }
                        res = mt5.order_send(req)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            log.info(
                                f"[NEXUS AUTONOMOUS FILL] #{res.order} {real_sym} {bias} {calc['lot']:.2f}L @ {spot:,.{d}f} | "
                                f"Magic={MAGIC_SOVEREIGN} | Score={score}/100 RSI={data.get('rsi')} | SL={sl:,.{d}f} TP={tp:,.{d}f}"
                            )
                            positions = list(mt5.positions_get() or [])
                        else:
                            log.warning(f"[REJECTED] {real_sym} {bias}: {getattr(res, 'retcode', None)} {getattr(res, 'comment', '')}")

            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"T4 loop exception: {e}")
            time.sleep(5)

    mt5.shutdown()


if __name__ == "__main__":
    run_t4_sovereign()
