import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5

from nexus_ship_core import SLEEVES
from nexus_tripartite_60s_vision import SILO_CONFIG, resolve_symbol, analyze_asset
from nexus_wal_ledger import (
    init_ledger, upsert_heartbeat, sync_open_positions,
    mark_be_locked, reserve_order_intent, finalize_order_fill, get_conn
)
from macro_gate import check_macro_window

BE_TRIGGER_R = 1.00
PRE_NEWS_BE_R = 0.45       # Tighten profitable open trades to BE inside T-15m Tier-1 news window
TICK_GUARD_SEC = 0.50
SLIPPAGE_LEDGER = Path(r"C:\Quant-Nexus-Eng\execution_slippage_ledger.jsonl")

# Max spread caps (in points) & risk parameters per sleeve
MAX_SPREAD_PTS = {"T1": 3500, "T2": 25, "T3": 45}
RISK_PCT_PER_TRADE = {"T1": 0.0040, "T2": 0.0050, "T3": 0.0050}
T3_MAX_ATR_USD = 8.00
SL_ATR_MULT = 1.50
TP_R_MULT = 2.50

def connect_persistent_ipc(sleeve: str) -> bool:
    cfg = SLEEVES[sleeve]
    for attempt in range(1, 6):
        if mt5.initialize(
            path=cfg["path"],
            login=cfg["login"],
            password=cfg["password"],
            server=cfg["server"],
            timeout=180000,
        ):
            info = mt5.account_info()
            if info and info.login == cfg["login"]:
                print(f"[{sleeve}] Persistent IPC locked to #{info.login} (Eq=${info.equity:,.2f}) on attempt {attempt}")
                return True
        err = mt5.last_error()
        print(f"[{sleeve}] IPC connect attempt {attempt} failed: {err} — retrying in 3s...")
        mt5.shutdown()
        time.sleep(3.0)
    return False

def reconstruct_init_sl(ticket: int, fallback_sl: float) -> float:
    orders = mt5.history_orders_get(position=ticket) or []
    for o in sorted(orders, key=lambda x: x.time_setup):
        if float(o.sl) > 0.0:
            return float(o.sl)
    return fallback_sl

def append_slippage_jsonl(record: dict) -> None:
    try:
        with SLIPPAGE_LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception as exc:
        print(f"[WARN] Failed to append slippage ledger: {exc}")

def compute_atr_14(symbol: str, tf_lbl: str) -> float:
    tf = mt5.TIMEFRAME_M5 if tf_lbl == "M5" else mt5.TIMEFRAME_M15
    rates = mt5.copy_rates_from_pos(symbol, tf, 1, 15)
    if rates is None or len(rates) < 14:
        return 0.0
    trs = []
    for i in range(1, len(rates)):
        h, l, pc = float(rates[i]["high"]), float(rates[i]["low"]), float(rates[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-14:]) / 14.0

def normalize_volume(sinfo, raw_lots: float) -> float:
    step = float(sinfo.volume_step) or 0.01
    vmin = float(sinfo.volume_min) or 0.01
    vmax = float(sinfo.volume_max) or 10.0
    steps = int(raw_lots / step)
    vol = round(steps * step, 2)
    return max(vmin, min(vmax, vol))

def mark_intent_rejected(client_order_id: str, reason: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute(
            "UPDATE order_intents SET state='REJECTED', regime_json=json_set(regime_json, '$.reject_reason', ?), updated_utc=? WHERE client_order_id=?;",
            (reason, now, client_order_id),
        )
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
    finally:
        conn.close()

def execute_bar_close_entry(sleeve: str, ev: dict, tf_lbl: str, equity: float, now_utc: datetime) -> bool:
    raw_sym = ev["raw_symbol"]
    mt5_sym = ev["symbol"]
    direction = ev["direction"]
    score = float(ev["score"])

    # 1. Proactive Tier-1 Macro Blackout Check
    macro_blocked, macro_reason, _ = check_macro_window(raw_sym, now_utc)
    if macro_blocked:
        print(f"[{sleeve}] [BLOCKED] {raw_sym} {direction} ({score:.0f}%) -> {macro_reason}")
        return False

    sinfo = mt5.symbol_info(mt5_sym)
    tick = mt5.symbol_info_tick(mt5_sym)
    if not sinfo or not tick or not sinfo.visible:
        return False

    # 2. SPR-SHIELD Spread Check
    spread_pts = int(round((float(tick.ask) - float(tick.bid)) / float(sinfo.point)))
    if spread_pts > MAX_SPREAD_PTS[sleeve]:
        print(f"[{sleeve}] [SPR-SHIELD] {raw_sym} spread {spread_pts} pts > cap {MAX_SPREAD_PTS[sleeve]} pts")
        return False

    # 3. ATR Volatility & T3 $8.00 ATR-CAP Check
    atr = compute_atr_14(mt5_sym, tf_lbl)
    if atr <= 0.0:
        return False
    if sleeve == "T3" and atr > T3_MAX_ATR_USD:
        print(f"[{sleeve}] [ATR-CAP] {raw_sym} M15 ATR=${atr:.2f} > ${T3_MAX_ATR_USD:.2f} cap")
        return False

    # 4. Compute SL, TP, and Risk-Normalized Lot Size
    is_buy = (direction == "BUY")
    entry_req = float(tick.ask) if is_buy else float(tick.bid)
    sl_dist = atr * SL_ATR_MULT
    tp_dist = sl_dist * TP_R_MULT

    init_sl = round(entry_req - sl_dist, sinfo.digits) if is_buy else round(entry_req + sl_dist, sinfo.digits)
    init_tp = round(entry_req + tp_dist, sinfo.digits) if is_buy else round(entry_req - tp_dist, sinfo.digits)

    tick_val = float(sinfo.trade_tick_value) or 1.0
    tick_sz = float(sinfo.trade_tick_size) or float(sinfo.point)
    risk_usd = equity * RISK_PCT_PER_TRADE[sleeve]
    loss_per_lot = (sl_dist / tick_sz) * tick_val
    if loss_per_lot <= 0.0:
        return False
    lots = normalize_volume(sinfo, risk_usd / loss_per_lot)

    # 5. Atomic SQLite Intent Reservation + Fleet USD Factor Cap Check
    cid = f"{sleeve}_{raw_sym}_{now_utc.strftime('%Y%m%d_%H%M')}_{direction}"
    regime_meta = {
        "mom_state": ev.get("mom_state"),
        "tsmom_z": ev.get("tsmom_z"),
        "ou_state": ev.get("ou_state"),
        "ou_z": ev.get("ou_z"),
        "gm_state": ev.get("gm_state"),
        "gamma_regime": ev.get("gamma_regime"),
        "spread_pts": spread_pts,
        "atr": round(atr, sinfo.digits),
    }
    ok, res_msg = reserve_order_intent(
        cid, sleeve, raw_sym, direction, lots, entry_req, init_sl, init_tp, score, regime_meta
    )
    if not ok:
        print(f"[{sleeve}] [INTENT-DENIED] {cid} -> {res_msg}")
        return False

    # 6. Dispatch Market Order to Persistent MT5 IPC
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": mt5_sym,
        "volume": lots,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": entry_req,
        "sl": init_sl,
        "tp": init_tp,
        "deviation": 20,
        "magic": 700000 + int(sleeve[1]),
        "comment": cid[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if not res or res.retcode != mt5.TRADE_RETCODE_DONE:
        err_code = res.retcode if res else mt5.last_error()
        mark_intent_rejected(cid, f"MT5_RETCODE_{err_code}")
        print(f"[{sleeve}] [ORDER-FAIL] {cid} retcode={err_code}")
        return False

    # 7. Finalize Fill in SQLite WAL & Append Slippage Telemetry
    fill_px = float(res.price) if float(res.price) > 0.0 else entry_req
    # Adverse slippage in points (>0 means worse fill than requested)
    raw_slip = (fill_px - entry_req) if is_buy else (entry_req - fill_px)
    slip_pts = round(raw_slip / float(sinfo.point), 2)
    ticket = int(res.order)

    # Resolve live position ticket if broker assigns separate position ID
    for p in (mt5.positions_get(symbol=mt5_sym) or []):
        if p.comment == cid[:31] or p.ticket == ticket:
            ticket = int(p.ticket)
            fill_px = float(p.price_open)
            break

    finalize_order_fill(cid, ticket, fill_px, slip_pts)
    append_slippage_jsonl({
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "client_order_id": cid,
        "sleeve": sleeve,
        "ticket": ticket,
        "symbol": raw_sym,
        "direction": direction,
        "volume": lots,
        "score": score,
        "entry_req": entry_req,
        "fill_price": fill_px,
        "slippage_pts": slip_pts,
        "spread_pts": spread_pts,
        "regime": regime_meta,
    })
    print(
        f"[{sleeve}] [FILLED] #{ticket} {raw_sym} {direction} {lots:.2f}L @ {fill_px:.{sinfo.digits}f} "
        f"(Slip={slip_pts:+.1f}pts | SL={init_sl:.{sinfo.digits}f} | TP={init_tp:.{sinfo.digits}f})"
    )
    return True

def run_500ms_tick_guard(sleeve: str, pid: int) -> int:
    acc = mt5.account_info()
    if acc is None:
        raise RuntimeError("IPC_DISCONNECTED")

    positions = mt5.positions_get() or []
    live_map = {}
    for p in positions:
        direction = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
        init_sl = reconstruct_init_sl(p.ticket, float(p.sl))
        live_map[p.ticket] = {
            "raw_symbol": p.symbol,
            "direction": direction,
            "volume": float(p.volume),
            "entry": float(p.price_open),
            "sl": float(p.sl),
            "tp": float(p.tp),
            "init_sl": init_sl,
        }

    managed = sync_open_positions(sleeve, live_map)
    now_utc = datetime.now(timezone.utc)

    for tkt, pos in live_map.items():
        meta = managed[tkt]
        tick = mt5.symbol_info_tick(pos["raw_symbol"])
        sinfo = mt5.symbol_info(pos["raw_symbol"])
        if not tick or not sinfo:
            continue

        entry = float(meta["entry_price"])
        init_sl = float(meta["init_sl"])
        risk_dist = abs(entry - init_sl)
        if risk_dist <= 0.0:
            continue

        is_buy = (pos["direction"] == "BUY")
        cur_px = float(tick.bid) if is_buy else float(tick.ask)
        move_dist = (cur_px - entry) if is_buy else (entry - cur_px)
        true_r = move_dist / risk_dist

        # Standard +1.00R BE trigger OR early +0.45R BE protection inside Tier-1 macro blackout
        macro_blocked, macro_reason, _ = check_macro_window(pos["raw_symbol"], now_utc)
        active_be_r = PRE_NEWS_BE_R if macro_blocked else BE_TRIGGER_R

        if true_r >= active_be_r and int(meta["be_locked"]) == 0:
            be_buffer = sinfo.point * 5
            be_sl = round(entry + be_buffer, sinfo.digits) if is_buy else round(entry - be_buffer, sinfo.digits)
            needs_mod = (pos["sl"] < be_sl) if is_buy else (pos["sl"] == 0.0 or pos["sl"] > be_sl)
            if needs_mod:
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": tkt,
                    "symbol": pos["raw_symbol"],
                    "sl": be_sl,
                    "tp": pos["tp"],
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    mark_be_locked(tkt, be_sl, true_r)
                    tag = f"PRE-NEWS BE ({macro_reason})" if macro_blocked else "BE-LOCKED"
                    print(f"[{sleeve}] [{tag} @ {true_r:+.2f}R] #{tkt} {pos['raw_symbol']} SL -> {be_sl:.{sinfo.digits}f}")

    upsert_heartbeat(sleeve, pid, acc.login, float(acc.equity), len(positions), "RUNNING")
    return len(positions)

def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in SLEEVES:
        print("Usage: python nexus_sleeve_worker.py <T1|T2|T3>")
        sys.exit(1)

    sleeve = sys.argv[1]
    pid = os.getpid()
    scfg = SILO_CONFIG[sleeve]
    tf_mins = 5 if sleeve == "T1" else 15
    last_bar_bucket = -1

    init_ledger()
    if not connect_persistent_ipc(sleeve):
        sys.exit(2)

    try:
        while True:
            t0 = time.monotonic()
            try:
                open_cnt = run_500ms_tick_guard(sleeve, pid)
            except RuntimeError:
                print(f"[{sleeve}] IPC lost — reconnecting...")
                mt5.shutdown()
                if not connect_persistent_ipc(sleeve):
                    sys.exit(3)
                continue

            now_utc = datetime.now(timezone.utc)
            bar_bucket = (now_utc.hour * 60 + now_utc.minute) // tf_mins

            if bar_bucket != last_bar_bucket and now_utc.second >= 1:
                last_bar_bucket = bar_bucket
                kz_open = (now_utc.hour in scfg["utc_hours"])
                evs = []
                for candidates, tf_lbl in scfg["assets"]:
                    sym = resolve_symbol(candidates)
                    if sym:
                        evs.append(analyze_asset(sym, sleeve, tf_lbl))

                if sleeve == "T2" and len(evs) >= 4:
                    evs.sort(key=lambda x: x.get("tsmom_z", 0.0), reverse=True)

                acc = mt5.account_info()
                eq = float(acc.equity) if acc else 0.0

                for ev in evs:
                    sc = float(ev["score"])
                    direction = ev["direction"]
                    if kz_open and open_cnt == 0 and direction in ("BUY", "SELL") and scfg["gate"] <= sc <= scfg["max_score"]:
                        tf_lbl = "M5" if sleeve == "T1" else "M15"
                        if execute_bar_close_entry(sleeve, ev, tf_lbl, eq, now_utc):
                            open_cnt = 1
                            break

                upsert_heartbeat(sleeve, pid, SLEEVES[sleeve]["login"], eq, open_cnt, "RUNNING", now_utc.isoformat())

            elapsed = time.monotonic() - t0
            time.sleep(max(0.05, TICK_GUARD_SEC - elapsed))
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
