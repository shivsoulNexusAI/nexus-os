"""
QUANT-NEXUS TERMINAL 4 (T4) // EXACT 11/16/2026 LAPTOP MASTER ENGINE (#278060961)
100% Verbatim Port of core/telegram_interactive.py (11/16/2026) + core/stacking_engine.py (11/04/2026):
- Assets: ["EURUSD", "BTCUSD", "XAUUSD", "GBPUSD", "USDJPY"]
- 15-Second Continuous Multi-Asset Scan Loop
- Exact M15 MA10 Imbalance Model: raw_delta = (curr_close - ma10) / ma10 (> +/- 0.0003)
- Exact Edge Formula: min(96, int(65 + abs(raw_delta) * 8000)) >= 72
- Exact Spread-Multiple SL/TP: SL = spread * 30 | TP = spread * 65
- Exact Lot Sizing: round(max(0.01, min(5.0, (equity * 0.01) / 300)), 2) (BTC 0.50L with margin-safe cap)
- Exact Fingerprint: magic=999888, comment="Nexus Autonomous"
- Pillar 1 Asymmetric Invalidation Stacker (0.5x M5 swing add-on at >= +1.2R BE) + -$300 Daily Circuit Breaker
"""
import os
import sys
import time
import json
import sqlite3
import logging
from datetime import datetime, timezone
import numpy as np
import MetaTrader5 as mt5

T4_MT5_PATH = r"C:\MT5_Sovereign_T4\terminal64.exe"
LEDGER_DB = r"C:\Quant-Nexus-Eng\nexus_ledger.db"
STATE_FILE = r"C:\Quant-Nexus-Eng\t4_sovereign_state.json"
LOG_FILE = r"C:\Quant-Nexus-Eng\logs\t4_sovereign_apex.log"

ASSETS = ["EURUSD", "BTCUSD", "XAUUSD", "GBPUSD", "USDJPY"]
MIN_EDGE = 72
SCAN_INTERVAL_SEC = 15.0
MAGIC_NEXUS = 999888
ORDER_COMMENT = "Nexus Autonomous"
DAILY_MAX_LOSS_LIMIT = -300.00

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [T4-NEXUS-1116] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("T4_Nexus_1116")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"banked_tickets": []}


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def get_filling_mode(s_info) -> int:
    mode_mask = s_info.filling_mode
    if mode_mask & 1:
        return mt5.ORDER_FILLING_FOK
    if mode_mask & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def check_daily_circuit_breaker() -> tuple[bool, str]:
    try:
        now = datetime.now()
        midnight_ts = datetime(now.year, now.month, now.day, 0, 0, 0).timestamp()
        deals = mt5.history_deals_get(midnight_ts, now.timestamp()) or []
        closed = [d for d in deals if d.entry == 1 and abs(d.profit) > 0.0001]
        tot_profit = sum(d.profit for d in closed)
        if tot_profit <= DAILY_MAX_LOSS_LIMIT:
            return True, f"Daily loss ${tot_profit:.2f} breached ${DAILY_MAX_LOSS_LIMIT:.2f}"
        return False, "NORMAL"
    except Exception:
        return False, "NORMAL"


def execute_market_order(symbol: str, direction: str, lot: float = 0.01, sl: float = 0.0, tp: float = 0.0, comment: str = ORDER_COMMENT):
    cb_tripped, cb_reason = check_daily_circuit_breaker()
    if cb_tripped:
        log.warning(f"ORDER REJECTED BY CIRCUIT BREAKER: {cb_reason}")
        return False, cb_reason, 0

    mt5.symbol_select(symbol, True)
    s_info = mt5.symbol_info(symbol)
    if not s_info:
        return False, f"No symbol_info for {symbol}", 0

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False, f"No tick for {symbol}", 0

    is_buy = direction.upper() == "BUY"
    price = tick.ask if is_buy else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    filling_mode = get_filling_mode(s_info)

    # Margin-safe guard so 0.50L BTC scales gracefully if free margin on $1,000 T4 is tight
    use_lot = float(lot)
    acc = mt5.account_info()
    if acc and use_lot > s_info.volume_min:
        margin_req = mt5.order_calc_margin(order_type, symbol, use_lot, price)
        if margin_req and margin_req > (acc.margin_free * 0.70):
            step = s_info.volume_step or 0.01
            safe_lot = int(((acc.margin_free * 0.65) / margin_req) * use_lot / step) * step
            use_lot = round(max(s_info.volume_min, safe_lot), 2)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(use_lot),
        "type": order_type,
        "price": float(price),
        "deviation": 50,
        "magic": MAGIC_NEXUS,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    if sl > 0:
        request["sl"] = float(sl)
    if tp > 0:
        request["tp"] = float(tp)

    res = mt5.order_send(request)
    if res is None:
        return False, f"order_send None: {mt5.last_error()}", 0
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        for alt_mode in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC]:
            if alt_mode != filling_mode:
                request["type_filling"] = alt_mode
                alt_res = mt5.order_send(request)
                if alt_res and alt_res.retcode == mt5.TRADE_RETCODE_DONE:
                    return True, f"Ticket #{alt_res.order}", alt_res.order
        return False, f"retcode={res.retcode} ({res.comment})", 0

    return True, f"Ticket #{res.order}", res.order


def calculate_asset_edge(symbol: str):
    """Exact 11/16/2026 telegram_interactive.py calculate_asset_edge()."""
    mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return None

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)
    if rates is None or len(rates) < 10:
        return None

    closes = rates["close"]
    ma10 = float(sum(closes[-10:])) / 10.0
    curr_close = float(closes[-1])
    raw_delta = (curr_close - ma10) / ma10

    s_info = mt5.symbol_info(symbol)
    digits = s_info.digits if s_info else (5 if "USD" in symbol and symbol != "BTCUSD" else 2)
    spread = float(tick.ask - tick.bid)

    if raw_delta > 0.0003:
        direction = "BUY"
        edge = min(96, int(65 + abs(raw_delta) * 8000))
        entry_price = round(float(tick.ask), digits)
        sl = round(entry_price - (spread * 30), digits)
        tp = round(entry_price + (spread * 65), digits)
    elif raw_delta < -0.0003:
        direction = "SELL"
        edge = min(96, int(65 + abs(raw_delta) * 8000))
        entry_price = round(float(tick.bid), digits)
        sl = round(entry_price + (spread * 30), digits)
        tp = round(entry_price - (spread * 65), digits)
    else:
        direction = "NEUTRAL"
        edge = 50
        entry_price = round(float(tick.bid), digits)
        sl, tp = entry_price, entry_price

    cleared = edge >= MIN_EDGE and direction != "NEUTRAL"

    acc = mt5.account_info()
    equity = float(acc.equity) if acc else 1000.0
    lots = round(max(0.01, min(5.0, (equity * 0.01) / 300.0)), 2)
    if "BTC" in symbol:
        lots = 0.50

    return {
        "symbol": symbol,
        "direction": direction,
        "edge": edge,
        "calculated_lots": lots,
        "cleared": cleared,
        "price": entry_price,
        "sl": sl,
        "tp": tp,
    }


def evaluate_stacking_opportunity(symbol: str) -> dict:
    """Exact 11/04/2026 core/stacking_engine.py Pillar 1 Asymmetric Stacker."""
    positions = mt5.positions_get(symbol=symbol) or []
    if not positions:
        return {"eligible": False}

    parent_pos = None
    existing_stacks = []
    for p in positions:
        if "STACK" in (p.comment or ""):
            existing_stacks.append(p)
        else:
            parent_pos = p

    if existing_stacks or not parent_pos:
        return {"eligible": False}

    is_be = abs(parent_pos.sl - parent_pos.price_open) < 0.001
    if not is_be:
        return {"eligible": False}

    risk_dist = 0.0020
    if "JPY" in symbol:
        risk_dist = 0.200
    elif "XAU" in symbol:
        risk_dist = 5.00
    elif "BTC" in symbol:
        risk_dist = 150.0

    current_dist = (parent_pos.price_current - parent_pos.price_open) if parent_pos.type == 0 else (parent_pos.price_open - parent_pos.price_current)
    current_r = current_dist / risk_dist
    if current_r < 1.2:
        return {"eligible": False}

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 20)
    if rates is None or len(rates) < 10:
        return {"eligible": False}

    direction = "BUY" if parent_pos.type == 0 else "SELL"
    stack_lot = max(0.01, round(parent_pos.volume * 0.5, 2))
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"eligible": False}

    s_info = mt5.symbol_info(symbol)
    digits = s_info.digits if s_info else 5

    if direction == "BUY":
        sl = float(np.min(rates["low"][-5:]))
        entry = float(tick.ask)
        if sl >= entry or (entry - sl) > (risk_dist * 1.5):
            sl = entry - (risk_dist * 0.8)
        tp = entry + (abs(entry - sl) * 2.5)
    else:
        sl = float(np.max(rates["high"][-5:]))
        entry = float(tick.bid)
        if sl <= entry or (sl - entry) > (risk_dist * 1.5):
            sl = entry + (risk_dist * 0.8)
        tp = entry - (abs(sl - entry) * 2.5)

    return {
        "eligible": True,
        "symbol": symbol,
        "direction": direction,
        "lot": stack_lot,
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "parent_ticket": parent_pos.ticket,
        "parent_r": round(current_r, 2),
    }


def manage_breakeven_and_trailing():
    """Protects open positions at Breakeven once +1.0R in profit so stacking_engine unlocks."""
    for p in (mt5.positions_get() or []):
        s_info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not s_info or not tick:
            continue
        digits = s_info.digits
        is_buy = (p.type == 0)
        curr_px = float(tick.bid if is_buy else tick.ask)
        entry = float(p.price_open)
        init_risk = abs(entry - float(p.sl)) if p.sl > 0 else 0.0
        if init_risk <= 0:
            continue
        gain = (curr_px - entry) if is_buy else (entry - curr_px)
        be_px = round(entry, digits)
        if gain >= init_risk:
            if (is_buy and p.sl < be_px) or (not is_buy and p.sl > be_px):
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "sl": be_px,
                    "tp": p.tp,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log.info(f"[AUTO-BE LOCK] #{p.ticket} {p.symbol} SL moved to exact entry {be_px}")


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


def run_t4_nexus_1116():
    if not mt5.initialize(path=T4_MT5_PATH, login=278071462, password=r"H@ngkook3695", server="Exness-MT5Trial5", portable=True):
        log.error(f"MT5 T4 init/login failed: {mt5.last_error()}")
        return
    acct_chk = mt5.account_info()
    if not acct_chk or acct_chk.login != 278071462:
        mt5.login(278071462, password=r"H@ngkook3695", server="Exness-MT5Trial5")

    acct = mt5.account_info()
    log.info(
        f"T4 NEXUS AUTONOMOUS (11/16/2026 EXACT LAPTOP ENGINE) ONLINE | Account=#{acct.login} | "
        f"Equity=${acct.equity:.2f} | Assets={ASSETS} | MinEdge={MIN_EDGE}% | Magic={MAGIC_NEXUS} | Cycle=15s"
    )

    cycle_num = 0
    while True:
        try:
            acct = mt5.account_info()
            if not acct:
                time.sleep(3)
                continue

            manage_breakeven_and_trailing()

            scans = []
            for sym in ASSETS:
                res = calculate_asset_edge(sym)
                if res:
                    scans.append(res)
            scans.sort(key=lambda x: x.get("edge", 0), reverse=True)

            cb_active, _ = check_daily_circuit_breaker()
            if not cb_active:
                for candidate in scans:
                    sym = candidate["symbol"]
                    edge = candidate["edge"]
                    direction = candidate["direction"]
                    cleared = candidate.get("cleared", False)

                    positions = mt5.positions_get(symbol=sym)
                    is_locked = positions and len(positions) > 0

                    if cleared and not is_locked:
                        lots = candidate.get("calculated_lots", 0.01)
                        sl = candidate.get("sl", 0.0)
                        tp = candidate.get("tp", 0.0)
                        ok, msg, ticket = execute_market_order(sym, direction, lot=lots, sl=sl, tp=tp, comment=ORDER_COMMENT)
                        if ok:
                            log.info(
                                f"[INSTANT-TRIGGER] #{ticket} {sym} {direction} ({lots}L @ {edge}% Edge) | "
                                f"Entry={candidate['price']} SL={sl} TP={tp} | Magic={MAGIC_NEXUS}"
                            )
                        else:
                            log.warning(f"[REJECTED] {sym} {direction} ({lots}L @ {edge}%): {msg}")

            # Pillar 1: Asymmetric Invalidation Stacking Scanner
            for s_sym in ASSETS:
                st_res = evaluate_stacking_opportunity(s_sym)
                if st_res.get("eligible"):
                    ok_st, st_msg, st_ticket = execute_market_order(
                        s_sym, st_res["direction"], lot=st_res["lot"], sl=st_res["sl"], tp=st_res["tp"],
                        comment=f"Nexus Autonomous STACK #{st_res['parent_ticket']}"
                    )
                    if ok_st:
                        log.info(f"[ASYMMETRIC STACK] #{st_ticket} {s_sym} {st_res['direction']} {st_res['lot']}L behind Parent #{st_res['parent_ticket']}")

            live_pos = list(mt5.positions_get() or [])
            status_str = f"MANAGING_ACTIVE({len(live_pos)})" if live_pos else "ACTIVE_NEXUS_15S(Open:0)"
            update_heartbeat(acct.login, acct.equity, len(live_pos), status_str)

            cycle_num += 1
            if cycle_num % 4 == 1 and scans:
                summary = " | ".join(f"{s['symbol']}:{s['direction']}({s['edge']}%)" for s in scans)
                log.info(f"[15s-SCAN] {summary} | Open={len(live_pos)}")

            time.sleep(SCAN_INTERVAL_SEC)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"T4 15s daemon exception: {e}")
            time.sleep(5)

    mt5.shutdown()


if __name__ == "__main__":
    run_t4_nexus_1116()
