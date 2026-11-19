"""
QUANT-NEXUS TERMINAL 4 (T4) // SOVEREIGN APEX NODE (v14.0)
Dedicated XAUUSD + BTCUSD + EURUSD Engine:
- Additive Confluence Scoring (>= 80.0 / 100)
- 1.0% Equity-Parity Risk Sizing (1.5x M15 ATR SL / 3.0x M15 ATR TP = 1:2 R:R)
- 1.0x ATR Zero-Touch BE (+2 pips) -> 1.2x ATR 50% Partial Bank -> 1.5x ATR Chandelier Trail
- 4h Soft Choke / 8h Alpha Half-Life Decay Reaper
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

MAGIC_T4 = 999888
WATCHLIST = ["XAUUSD", "BTCUSD", "EURUSD"]
RISK_PCT = 0.01          # 1.0% Equity-Parity Risk per trade
CONFLUENCE_GATE = 80.0   # Triggers >= 80.0 / 100
MAX_SLOTS = 3            # Max 1 slot per symbol (XAUUSD, BTCUSD, EURUSD)
HALF_LIFE_SEC = 14400    # 4h soft risk choke
TERMINAL_SEC = 28800     # 8h stagnation reaper

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [T4-SOVEREIGN] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("T4_Sovereign")


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
        log.warning(f"State persist failed: {e}")


def resolve_symbol(base: str) -> str | None:
    for cand in (base, f"{base}m", f"{base}.raw", f"{base}_i", f"{base}c"):
        info = mt5.symbol_info(cand)
        if info and info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED and not cand.endswith("_x10"):
            mt5.symbol_select(cand, True)
            tick = mt5.symbol_info_tick(cand)
            if tick and tick.bid > 0:
                return cand
    return None


def compute_m15_atr(symbol: str, period: int = 14) -> float:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, period + 15)
    if rates is None or len(rates) < period + 1:
        return 0.0
    highs = rates["high"]
    lows = rates["low"]
    closes = rates["close"]
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    return float(np.mean(tr[-period:]))


def compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def evaluate_sovereign_confluence(symbol: str, atr_m15: float) -> tuple[float, str, float]:
    """Recovered Sovereign Apex Additive Confluence Matrix (0 - 96.5, triggers >= 80.0)."""
    now_utc = datetime.now(timezone.utc)
    hhmm = now_utc.hour * 60 + now_utc.minute
    if (21 * 60 + 50) <= hhmm <= (23 * 60 + 15):
        return 50.0, "NEUTRAL", 50.0

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
    tick = mt5.symbol_info_tick(symbol)
    if rates is None or len(rates) < 20 or not tick or tick.bid <= 0:
        return 50.0, "NEUTRAL", 50.0

    closes = rates["close"]
    highs = rates["high"]
    lows = rates["low"]
    curr_c = float(closes[-1])
    rsi = compute_rsi(closes, 14)

    bull_pts, bear_pts = 0.0, 0.0

    if rsi < 32.0:
        bull_pts += 35.0
    elif rsi > 68.0:
        bear_pts += 35.0
    elif 40.0 <= rsi <= 55.0:
        bull_pts += 20.0
    elif 45.0 <= rsi <= 60.0:
        bear_pts += 20.0

    if curr_c > float(np.max(highs[-10:-1])):
        bull_pts += 25.0
    elif curr_c < float(np.min(lows[-10:-1])):
        bear_pts += 25.0

    sp_px = float(tick.ask - tick.bid)
    if sp_px > 0 and atr_m15 > 0 and (atr_m15 / sp_px) >= 4.0:
        bull_pts += 15.0
        bear_pts += 15.0

    if bull_pts > bear_pts:
        score = min(96.5, round(50.0 + (bull_pts * 0.48), 1))
        return score, ("BUY" if score >= CONFLUENCE_GATE else "NEUTRAL"), round(rsi, 1)
    elif bear_pts > bull_pts:
        score = min(96.5, round(50.0 + (bear_pts * 0.48), 1))
        return score, ("SELL" if score >= CONFLUENCE_GATE else "NEUTRAL"), round(rsi, 1)
    return 50.0, "NEUTRAL", round(rsi, 1)


def compute_equity_parity_lot(equity: float, symbol: str, sl_dist: float) -> float:
    info = mt5.symbol_info(symbol)
    if not info or sl_dist <= 0 or info.point <= 0 or info.trade_tick_size <= 0:
        return 0.01
    risk_cash = equity * RISK_PCT
    ticks_at_risk = sl_dist / info.trade_tick_size
    cash_per_lot = ticks_at_risk * info.trade_tick_value
    if cash_per_lot <= 0:
        return info.volume_min
    raw_lot = risk_cash / cash_per_lot
    step = info.volume_step or 0.01
    norm_lot = round(raw_lot / step) * step
    return round(max(info.volume_min, min(info.volume_max, norm_lot)), 2)


def get_filling_mode(info) -> int:
    if info.filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    if info.filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


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
    """4-Stage Sovereign Sentry: 1.0x ATR BE+2pips -> 1.2x ATR 50% Bank -> 1.5x ATR Chandelier -> 4h/8h Decay."""
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
                    "magic": MAGIC_T4, "comment": "THETA_REAP_8H",
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
                    "magic": MAGIC_T4, "comment": f"Nexus_TP1_50pct_{ticket}",
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
    log.info(f"T4 SOVEREIGN APEX ONLINE | Account=#{acct.login} | Equity=${acct.equity:.2f} | Assets={WATCHLIST}")
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
            if (now_ts - last_scan_ts) >= 10.0 and len(positions) < MAX_SLOTS:
                last_scan_ts = now_ts
                for base in WATCHLIST:
                    if any(base in p.symbol.upper() for p in positions):
                        continue
                    sym = resolve_symbol(base)
                    if not sym:
                        continue
                    atr_m15 = compute_m15_atr(sym, 14)
                    if atr_m15 <= 0:
                        continue

                    score, bias, rsi = evaluate_sovereign_confluence(sym, atr_m15)
                    if score >= CONFLUENCE_GATE and bias in ("BUY", "SELL"):
                        info = mt5.symbol_info(sym)
                        tick = mt5.symbol_info_tick(sym)
                        if not info or not tick:
                            continue
                        digits = info.digits
                        sl_dist = 1.5 * atr_m15
                        tp_dist = 3.0 * atr_m15
                        spot = tick.ask if bias == "BUY" else tick.bid
                        sl = round(spot - sl_dist if bias == "BUY" else spot + sl_dist, digits)
                        tp = round(spot + tp_dist if bias == "BUY" else spot - tp_dist, digits)
                        lot = compute_equity_parity_lot(float(acct.equity), sym, sl_dist)

                        req = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": sym,
                            "volume": lot,
                            "type": mt5.ORDER_TYPE_BUY if bias == "BUY" else mt5.ORDER_TYPE_SELL,
                            "price": spot,
                            "sl": sl,
                            "tp": tp,
                            "deviation": 30,
                            "magic": MAGIC_T4,
                            "comment": "Nexus Autonomous",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": get_filling_mode(info),
                        }
                        res = mt5.order_send(req)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            log.info(
                                f"[SOVEREIGN FILL] #{res.order} {sym} {bias} {lot:.2f}L @ {spot} | "
                                f"SL={sl} TP={tp} (1:2 R:R) | Score={score}/100 RSI={rsi}"
                            )
                            positions = list(mt5.positions_get() or [])
                        else:
                            log.warning(f"[ORDER REJECTED] {sym} {bias}: {getattr(res, 'retcode', None)} {getattr(res, 'comment', '')}")

            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"T4 loop exception: {e}")
            time.sleep(5)

    mt5.shutdown()


if __name__ == "__main__":
    run_t4_sovereign()
