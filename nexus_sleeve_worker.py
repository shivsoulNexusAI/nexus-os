# -*- coding: utf-8 -*-
"""
SHIVSOUL NEXUS v10.2 // ADAPTIVE M5 HYBRID SCALPER + REAL-TIME TELEGRAM TELEMETRY
- T1 (#278062038): BTCUSD M5 Market Impulse & Liquidity Sweep Scalper
- T2 (#278062039): FX Majors M5 Market Scalper + 15-Min TTL Breakout Stop Orders
- T3 (#278062042): XAUUSD M5 Market Scalper + 15-Min TTL Breakout Stop Orders
"""
import os
import sys
import time
import sqlite3
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import MetaTrader5 as mt5

ROOT_DIR = Path(r"C:\Quant-Nexus-Eng")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Load Telegram credentials dynamically from local config modules
TG_TOKEN = ""
TG_CHAT_ID = ""
for cfg_mod in ("telegram_nexus_config", "telegram_config", "nexus_tg_config"):
    try:
        m = __import__(cfg_mod)
        TG_TOKEN = getattr(m, "BOT_TOKEN", getattr(m, "TELEGRAM_BOT_TOKEN", getattr(m, "TOKEN", TG_TOKEN)))
        TG_CHAT_ID = str(getattr(m, "CHAT_ID", getattr(m, "TELEGRAM_CHAT_ID", getattr(m, "CHANNEL_ID", TG_CHAT_ID))))
        if TG_TOKEN and TG_CHAT_ID:
            break
    except Exception:
        pass

try:
    from telegram_notifier_v43 import send_v43_alert as _v43_send
except Exception:
    _v43_send = None

def send_nexus_tg(html_msg: str):
    """Non-blocking Telegram dispatch so network latency never stalls the 3s M5 scan loop."""
    def _worker():
        try:
            if _v43_send is not None:
                _v43_send(html_msg)
                return
            if TG_TOKEN and TG_CHAT_ID:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                with httpx.Client(timeout=6.0) as client:
                    client.post(url, json={
                        "chat_id": TG_CHAT_ID,
                        "text": html_msg,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    })
        except Exception as exc:
            logging.warning(f"[TG-ALERT] Dispatch warning: {exc}")

    threading.Thread(target=_worker, daemon=True).start()

try:
    from vpin_filter import VPINToxicityFilter
    vpin_guard = VPINToxicityFilter(adverse_threshold=0.68)
except Exception:
    vpin_guard = None

LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = ROOT_DIR / "nexus_ledger.db"

logging.basicConfig(
    filename=str(LOG_DIR / "nexus_worker.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

SLEEVE_CONFIGS = {
    "T1": {
        "name": "BTCUSD_M5_SMART_SCALP",
        "login": 278062038,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe",
        "symbols": ["BTCUSD"],
        "max_open": 1,
        "enable_pending_breakout": False,
        "max_pending": 0,
        "pending_ttl_mins": 15,
        "risk_pct": 0.005,
        "rr_target": 1.8,
        "max_spread_pts": 900,
        "active_hours": list(range(0, 21)),
    },
    "T2": {
        "name": "FX_MAJORS_M5_HYBRID_SCALP",
        "login": 278062039,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_Pending_278041169\terminal64.exe",
        "symbols": ["GBPUSD"],
        "max_open": 1,
        "enable_pending_breakout": True,
        "max_pending": 1,
        "pending_ttl_mins": 15,
        "risk_pct": 0.005,
        "rr_target": 1.8,
        "max_spread_pts": 22,
        "active_hours": list(range(1, 21)),
    },
    "T3": {
        "name": "XAUUSD_M5_HYBRID_GOLD",
        "login": 278062042,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_HFT_278041671\terminal64.exe",
        "symbols": ["XAUUSD"],
        "max_open": 1,
        "enable_pending_breakout": True,
        "max_pending": 1,
        "pending_ttl_mins": 15,
        "risk_pct": 0.005,
        "rr_target": 2.0,
        "max_spread_pts": 280,
        "active_hours": list(range(1, 22)),
    }
}

def resolve_symbol(base_sym: str) -> str | None:
    for candidate in (base_sym, base_sym + "m", base_sym + ".a"):
        info = mt5.symbol_info(candidate)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(candidate, True)
            return candidate
    return None

def get_filling_mode(sym_info):
    modes = sym_info.filling_mode
    if modes & 2:
        return mt5.ORDER_FILLING_IOC
    if modes & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN

def calc_ema(vals, period):
    k = 2.0 / (period + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = v * k + ema * (1.0 - k)
    return ema

def flatten_sleeve_positions(sleeve_key: str, reason: str = "DD_CIRCUIT_FLATTEN") -> int:
    """Closes all open positions on the active terminal immediately at market."""
    closed_count = 0
    for p in (mt5.positions_get() or []):
        sym_info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not sym_info or not tick:
            continue
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        close_px = float(tick.bid if is_buy else tick.ask)
        res = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "price": close_px,
            "deviation": 40,
            "magic": p.magic,
            "comment": "NX10_DD_Flat",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": get_filling_mode(sym_info),
        })
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed_count += 1
            logging.warning(f"[{sleeve_key}] Flattened #{p.ticket} ({p.symbol} {p.volume}L) @ {close_px} -> {reason}")
        else:
            logging.error(f"[{sleeve_key}] Failed to flatten #{p.ticket} ({p.symbol}): {getattr(res, 'retcode', mt5.last_error())}")
    return closed_count
def purge_nexus_pending_orders(sleeve_key: str, reason: str = "OCO_CLEANUP"):
    orders = mt5.orders_get() or []
    for o in orders:
        if o.magic == 202610:
            res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                logging.info(f"[{sleeve_key}] Cancelled pending #{o.ticket} ({o.symbol}) -> {reason}")

def evaluate_m5_setup(sleeve_key: str, symbol: str, rates, sym_info) -> dict | None:
    """v10.10 Production M15-Regime + Spread-Efficiency + Pruned Roster Evaluator."""
    if rates is None or len(rates) < 160:
        return None

    point = float(sym_info.point)
    digits = int(sym_info.digits)
    sp_pts = int(sym_info.spread)
    sp_px = sp_pts * point
    tick_val = float(sym_info.trade_tick_value) if sym_info.trade_tick_value > 0 else 1.0
    tick_size = float(sym_info.trade_tick_size) if sym_info.trade_tick_size > 0 else point
    lot = 0.02 if sleeve_key == "T2" else 0.01
    usd_per_price_unit = (tick_val / tick_size) * lot
    max_risk_usd = 4.50 if "BTC" in symbol.upper() else 99.0

    closes = [float(r["close"]) for r in rates]
    opens = [float(r["open"]) for r in rates]
    highs = [float(r["high"]) for r in rates]
    lows = [float(r["low"]) for r in rates]

    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(rates))
    ]
    atr = sum(trs[-14:]) / 14.0
    if atr <= 0 or atr < (5.0 * sp_px):
        return None

    def ema_series(vals, period):
        k = 2.0 / (period + 1)
        out = [vals[0]]
        for v in vals[1:]:
            out.append(v * k + out[-1] * (1.0 - k))
        return out

    ema9 = ema_series(closes, 9)
    ema21 = ema_series(closes, 21)
    ema60 = ema_series(closes, 60)
    ema150 = ema_series(closes, 150)

    htf_bull = ema60[-2] > ema150[-2] and ema60[-2] > ema60[-5]
    htf_bear = ema60[-2] < ema150[-2] and ema60[-2] < ema60[-5]

    o, h, l, c = opens[-2], highs[-2], lows[-2], closes[-2]
    swing_hi = max(highs[-10:-2])
    swing_lo = min(lows[-10:-2])
    box_h = swing_hi - swing_lo

    # T2 GBPUSD (0.02L): Liquidity-Sweep Reclaim Entry
    if sleeve_key == "T2":
        if htf_bull and l < swing_lo and c > swing_lo and c > o and (c - l) > 0.55 * (h - l):
            entry = round(closes[-1] + sp_px, digits)
            risk = max(entry - (l - 0.25 * atr), 1.25 * atr, 6.0 * sp_px)
            return {
                "order_kind": "MARKET", "direction": "BUY", "entry": entry,
                "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                "score": 85.0, "tag": "M5_SWEEP_RECLAIM_LONG"
            }
        if htf_bear and h > swing_hi and c < swing_hi and c < o and (h - c) > 0.55 * (h - l):
            entry = round(closes[-1], digits)
            risk = max((h + 0.25 * atr) - entry, 1.25 * atr, 6.0 * sp_px)
            return {
                "order_kind": "MARKET", "direction": "SELL", "entry": entry,
                "sl": round(entry + risk, digits), "tp": round(entry - 2.2 * risk, digits),
                "score": 85.0, "tag": "M5_SWEEP_RECLAIM_SHORT"
            }
        return None

    # T1 (BTCUSD/US30) & T3 (XAUUSD 07:00-20:00 UTC): M15-Aligned Hybrid Market + 15m TTL Stop
    bull = htf_bull and ema9[-2] > ema21[-2]
    bear = htf_bear and ema9[-2] < ema21[-2]

    if bull and c > swing_hi and (c - l) > 0.60 * atr:
        entry = round(closes[-1] + sp_px, digits)
        risk = max(1.30 * atr, 6.0 * sp_px)
        if risk * usd_per_price_unit <= max_risk_usd:
            return {
                "order_kind": "MARKET", "direction": "BUY", "entry": entry,
                "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                "score": 87.0, "tag": "M5_IMPULSE_LONG"
            }
    if bear and c < swing_lo and (h - c) > 0.60 * atr:
        entry = round(closes[-1], digits)
        risk = max(1.30 * atr, 6.0 * sp_px)
        if risk * usd_per_price_unit <= max_risk_usd:
            return {
                "order_kind": "MARKET", "direction": "SELL", "entry": entry,
                "sl": round(entry + risk, digits), "tp": round(entry - 2.2 * risk, digits),
                "score": 87.0, "tag": "M5_IMPULSE_SHORT"
            }

    if 0.25 * atr <= box_h <= 3.25 * atr:
        buf = 0.18 * atr
        if bull and swing_lo < c <= swing_hi:
            entry = round(swing_hi + buf + sp_px, digits)
            risk = max(1.25 * atr, 6.0 * sp_px)
            if risk * usd_per_price_unit <= max_risk_usd:
                return {
                    "order_kind": "PENDING_STOP", "direction": "BUY", "entry": entry,
                    "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                    "score": 82.0, "tag": "M5_BUY_STOP"
                }
        if bear and swing_lo <= c < swing_hi:
            entry = round(swing_lo - buf, digits)
            risk = max(1.25 * atr, 6.0 * sp_px)
            if risk * usd_per_price_unit <= max_risk_usd:
                return {
                    "order_kind": "PENDING_STOP", "direction": "SELL", "entry": entry,
                    "sl": round(entry + risk, digits), "tp": round(entry - 2.2 * risk, digits),
                    "score": 82.0, "tag": "M5_SELL_STOP"
                }
    return None

def guard_t3_pre_rollover(sleeve_key: str, cfg: dict, positions: list):
    """
    Protects open XAUUSD positions on T3 between 21:45 and 21:57 UTC before the 21:58 UTC daily break:
    - If floating positive: locks SL at breakeven + 60-pt pad.
    - If underwater or stop distance <= 450 pts ($4.50): flattens cleanly at market before liquidity drops.
    """
    if sleeve_key != "T3" or not positions:
        return

    for p in positions:
        if "XAUUSD" not in p.symbol.upper():
            continue
        sym_info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not sym_info or not tick:
            continue

        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        mark = float(tick.bid if is_buy else tick.ask)
        open_px = float(p.price_open)
        sl = float(p.sl)
        point = sym_info.point
        digits = sym_info.digits
        pad = 60 * point
        tight_limit = 450 * point

        gain = (mark - open_px) if is_buy else (open_px - mark)
        sl_dist_now = abs(mark - sl) if sl > 0 else 0.0

        # Case A: Floating in profit -> lock risk-free breakeven + pad
        if gain > pad:
            be_sl = round(open_px + pad if is_buy else open_px - pad, digits)
            needs_lock = (is_buy and (sl < be_sl or sl == 0.0)) or (not is_buy and (sl > be_sl or sl == 0.0))
            if needs_lock:
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "sl": be_sl,
                    "tp": p.tp
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    logging.info(f"[T3-ROLLOVER-GUARD] Locked BE SL on #{p.ticket} ({p.symbol}) -> {be_sl}")
                    send_nexus_tg(
                        f"🛡️ <b>[NEXUS T3 // PRE-ROLLOVER BE LOCK]</b>\n"
                        f"• Ticket: <code>#{p.ticket}</code> (<b>{p.symbol}</b>)\n"
                        f"• Action: Profitable runner locked at <code>{be_sl}</code> ahead of 21:58 UTC break."
                    )
            continue

        # Case B: Underwater or tight stop (<= $4.50) -> flatten before 21:58 UTC close
        if gain <= pad or sl == 0.0 or sl_dist_now <= tight_limit:
            close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "price": mark,
                "deviation": 40,
                "magic": p.magic,
                "comment": "NX10_PreRoll_Flat",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": get_filling_mode(sym_info),
            })
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                logging.info(f"[T3-ROLLOVER-GUARD] Flattened #{p.ticket} ({p.symbol}) @ {mark} before 21:58 UTC close")
                send_nexus_tg(
                    f"🧹 <b>[NEXUS T3 // PRE-ROLLOVER FLATTEN]</b>\n"
                    f"• Ticket: <code>#{p.ticket}</code> (<b>{p.symbol}</b> {p.volume}L)\n"
                    f"• Exit Price: <code>{mark}</code> (PnL: <code>{p.profit:+.2f}</code>)\n"
                    f"• Reason: Tight/underwater exposure closed safely before 21:58 UTC daily break."
                )
def update_heartbeat(sleeve: str, login: int, equity: float, open_count: int, status: str):
    try:
        conn = sqlite3.connect(LEDGER_PATH, timeout=5.0)
        conn.execute("""
            INSERT OR REPLACE INTO worker_heartbeats (sleeve, pid, login, equity, open_count, last_tick_utc, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sleeve, os.getpid(), login, equity, open_count, datetime.now(timezone.utc).isoformat(), status))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"[{sleeve}] Heartbeat DB error: {e}")

def log_intent(sleeve: str, symbol: str, direction: str, volume: float, entry: float, sl: float, tp: float, score: float, state: str, ticket: int = 0):
    try:
        conn = sqlite3.connect(LEDGER_PATH, timeout=5.0)
        now_iso = datetime.now(timezone.utc).isoformat()
        cid = f"{sleeve}_{symbol}_{int(time.time())}"
        conn.execute("""
            INSERT INTO order_intents (client_order_id, sleeve, symbol, direction, volume, entry_req, init_sl, init_tp, score, regime_json, state, mt5_ticket, created_utc, updated_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cid, sleeve, symbol, direction, volume, entry, sl, tp, score, "{}", state, ticket, now_iso, now_iso))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"[{sleeve}] Intent DB error: {e}")

def run_worker(sleeve_key: str):
    cfg = SLEEVE_CONFIGS[sleeve_key]
    if not mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"], portable=False):
        logging.error(f"[{sleeve_key}] MT5 init failed on {cfg['path']}: {mt5.last_error()}")
        sys.exit(1)

    logging.info(f"[{sleeve_key}] Hybrid M5 Scalper + Telegram Telemetry v10.2 ONLINE on #{cfg['login']}")
    last_bar_traded = {}
    tracked_pending_tickets = {}  # order_ticket -> dict metadata
    announced_open_tickets = set()
    dd_halt_alerted_date = None
    tracked_utc_day = None
    daily_dd_floor = 960.0

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            acct = mt5.account_info()
            if not acct:
                time.sleep(5)
                continue

            equity = float(acct.equity)
            positions = mt5.positions_get() or []
            pending_orders = [o for o in (mt5.orders_get() or []) if o.magic == 202610]
            open_count = len(positions)

            # Detect any pending stop order that triggered into a live position
            for p in positions:
                if p.magic == 202610 and p.ticket not in announced_open_tickets:
                    announced_open_tickets.add(p.ticket)
                    if p.ticket in tracked_pending_tickets:
                        meta = tracked_pending_tickets.pop(p.ticket)
                        p_dir = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                        send_nexus_tg(
                            f"⚡ <b>[NEXUS {sleeve_key} // PENDING BREAKOUT FILLED]</b>\n"
                            f"• Account: <code>#{cfg['login']}</code>\n"
                            f"• Asset: <b>{p.symbol}</b> ({p_dir} {p.volume}L)\n"
                            f"• Fill Price: <code>{p.price_open}</code> (Trigger: <code>{meta['trigger']}</code>)\n"
                            f"• SL: <code>{p.sl}</code> | TP: <code>{p.tp}</code>\n"
                            f"• Setup: <code>{meta['tag']}</code>"
                        )
                        log_intent(sleeve_key, p.symbol, p_dir, p.volume, p.price_open, p.sl, p.tp, meta["score"], "PENDING_FILLED", int(p.ticket))

            # Clean expired/cancelled tickets from tracked_pending_tickets
            live_pending_ids = {o.ticket for o in pending_orders}
            for stale_id in list(tracked_pending_tickets.keys()):
                if stale_id not in live_pending_ids:
                    tracked_pending_tickets.pop(stale_id, None)

            # Dynamic Daily DD Circuit Guard (4.0% max daily drawdown from UTC session start equity)
            today_str = now_utc.strftime("%Y-%m-%d")
            if tracked_utc_day != today_str:
                tracked_utc_day = today_str
                # Preserve T2 halt through 2026-11-18 UTC; otherwise set floor at 96.0% of session start equity
                if sleeve_key == "T2" and today_str == "2026-11-18" and equity < 960.0:
                    daily_dd_floor = 960.0
                else:
                    daily_dd_floor = round(equity * 0.96, 2)
                logging.info(f"[{sleeve_key}] UTC Day {today_str} Baseline Equity=${equity:.2f} | 4.0% DD Floor=${daily_dd_floor:.2f}")

            if equity <= daily_dd_floor:
                purged_cnt = len(pending_orders)
                if pending_orders:
                    purge_nexus_pending_orders(sleeve_key, "DD_CIRCUIT_HALT")
                closed_cnt = flatten_sleeve_positions(sleeve_key, "DD_CIRCUIT_HALT") if open_count > 0 else 0
                if dd_halt_alerted_date != today_str or closed_cnt > 0:
                    dd_halt_alerted_date = today_str
                    post_acct = mt5.account_info()
                    final_eq = float(post_acct.equity) if post_acct else equity
                    logging.warning(f"[{sleeve_key}] DD_CIRCUIT_HALT triggered at Equity=${final_eq:.2f} (<= ${daily_dd_floor:.2f}) | Flattened={closed_cnt}")
                    send_nexus_tg(
                        f"🚨 <b>[NEXUS {sleeve_key} // DD CIRCUIT HALT + FLATTEN]</b>\n"
                        f"• Account: <code>#{cfg['login']}</code> ({cfg['name']})\n"
                        f"• Equity: <b><code>${final_eq:.2f}</code></b> (4.0% Daily Floor: <code>${daily_dd_floor:.2f}</code>)\n"
                        f"• Flattened Positions: <b>{closed_cnt}</b> | Purged Pending: <b>{purged_cnt}</b>\n"
                        f"• Status: <b>FLAT & HALTED</b> until next UTC session reset."
                    )
                update_heartbeat(sleeve_key, cfg["login"], equity, len(mt5.positions_get() or []), "DD_CIRCUIT_HALT")
                time.sleep(30)
                continue

            # Exness Rollover Protection (21:45 - 00:15 UTC)
            if (now_utc.hour == 21 and now_utc.minute >= 45) or now_utc.hour in (22, 23) or now_utc.hour not in cfg["active_hours"]:
                if pending_orders:
                    purge_nexus_pending_orders(sleeve_key, "ROLLOVER_BLACKOUT")
                if now_utc.hour == 21 and 45 <= now_utc.minute <= 57:
                    guard_t3_pre_rollover(sleeve_key, cfg, positions)
                update_heartbeat(sleeve_key, cfg["login"], equity, len(mt5.positions_get() or []), "ROLLOVER_GUARD")
                time.sleep(15)
                continue

            # OCO Cleanup when a position is active
            if open_count >= cfg["max_open"]:
                if pending_orders:
                    purge_nexus_pending_orders(sleeve_key, "POSITION_FILLED_OCO")
                update_heartbeat(sleeve_key, cfg["login"], equity, open_count, "MANAGING_ACTIVE")
                time.sleep(5)
                continue

            for base_sym in cfg["symbols"]:
                if len(mt5.positions_get() or []) >= cfg["max_open"]:
                    break

                sym = resolve_symbol(base_sym)
                if not sym:
                    continue

                sym_info = mt5.symbol_info(sym)
                tick = mt5.symbol_info_tick(sym)
                if not sym_info or not tick or sym_info.spread > cfg["max_spread_pts"]:
                    continue

                m5_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 2)
                if m5_rates is None or len(m5_rates) < 2:
                    continue
                bar_ts = int(m5_rates[-1]["time"])
                if last_bar_traded.get(sym) == bar_ts:
                    continue

                setup = evaluate_m5_setup(sym)
                if not setup:
                    continue

                direction = setup["direction"]
                sl_dist = setup["sl_dist"]
                score = setup["score"]
                tag = setup["tag"]

                # Directional VPIN Adverse-Selection Filter
                if vpin_guard is not None:
                    v_res = vpin_guard.compute_directional_vpin(sym, direction, num_recent_ticks=3000)
                    if v_res.get("adverse_toxic"):
                        log_intent(sleeve_key, sym, direction, 0.0, 0.0, 0.0, 0.0, score, f"VPIN_VETO ({v_res.get('signed_vpin')})")
                        last_bar_traded[sym] = bar_ts
                        continue

                # Risk-calibrated position size (0.5% equity risk)
                risk_usd = equity * cfg["risk_pct"]
                tick_val = sym_info.trade_tick_value or 1.0
                tick_size = sym_info.trade_tick_size or sym_info.point
                sl_ticks = sl_dist / tick_size
                raw_lots = risk_usd / max(sl_ticks * tick_val, 0.01)
                step = sym_info.volume_step
                lots = max(sym_info.volume_min, min(0.10, round(round(raw_lots / step) * step, 2)))
                digits = sym_info.digits

                # === MODE A: IMMEDIATE MARKET SCALP ===
                if setup["mode"] == "MARKET":
                    if pending_orders:
                        purge_nexus_pending_orders(sleeve_key, "MARKET_STRIKE_OVERRIDE")

                    if direction == "BUY":
                        entry = tick.ask
                        sl = round(entry - sl_dist, digits)
                        tp = round(entry + (sl_dist * cfg["rr_target"]), digits)
                        order_type = mt5.ORDER_TYPE_BUY
                    else:
                        entry = tick.bid
                        sl = round(entry + sl_dist, digits)
                        tp = round(entry - (sl_dist * cfg["rr_target"]), digits)
                        order_type = mt5.ORDER_TYPE_SELL

                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": sym,
                        "volume": lots,
                        "type": order_type,
                        "price": entry,
                        "sl": sl,
                        "tp": tp,
                        "deviation": 35,
                        "magic": 202610,
                        "comment": f"NX10_{tag[:14]}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": get_filling_mode(sym_info),
                    })
                    last_bar_traded[sym] = bar_ts
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        ticket_id = int(res.order)
                        announced_open_tickets.add(ticket_id)
                        logging.info(f"[{sleeve_key}] MARKET {direction} {lots}L {sym} @ {res.price} | SL={sl} TP={tp}")
                        log_intent(sleeve_key, sym, direction, lots, entry, sl, tp, score, "EXECUTED_MARKET", ticket_id)
                        send_nexus_tg(
                            f"🚀 <b>[NEXUS {sleeve_key} // M5 MARKET SCALP]</b>\n"
                            f"• Account: <code>#{cfg['login']}</code>\n"
                            f"• Asset: <b>{sym}</b> ({direction} {lots}L)\n"
                            f"• Fill: <code>{res.price}</code> | Ticket: <code>#{ticket_id}</code>\n"
                            f"• SL: <code>{sl}</code> | TP: <code>{tp}</code> ({cfg['rr_target']}R)\n"
                            f"• Setup: <code>{tag}</code> (Score: {score})"
                        )
                        break

                # === MODE B: PENDING BREAKOUT STOP ORDER (T2 & T3) ===
                elif setup["mode"] == "PENDING" and cfg["enable_pending_breakout"]:
                    current_pending = [o for o in (mt5.orders_get() or []) if o.magic == 202610]
                    if len(current_pending) >= cfg["max_pending"]:
                        continue

                    stops_level_px = sym_info.trade_stops_level * sym_info.point
                    min_dist = max(stops_level_px * 1.2, 10 * sym_info.point)

                    if direction == "BUY":
                        trig = round(max(setup["trigger_price"], tick.ask + min_dist), digits)
                        sl = round(trig - sl_dist, digits)
                        tp = round(trig + (sl_dist * cfg["rr_target"]), digits)
                        p_type = mt5.ORDER_TYPE_BUY_STOP
                    else:
                        trig = round(min(setup["trigger_price"], tick.bid - min_dist), digits)
                        sl = round(trig + sl_dist, digits)
                        tp = round(trig - (sl_dist * cfg["rr_target"]), digits)
                        p_type = mt5.ORDER_TYPE_SELL_STOP

                    exp_ts = int((datetime.now(timezone.utc) + timedelta(minutes=cfg["pending_ttl_mins"])).timestamp())

                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_PENDING,
                        "symbol": sym,
                        "volume": lots,
                        "type": p_type,
                        "price": trig,
                        "sl": sl,
                        "tp": tp,
                        "deviation": 35,
                        "magic": 202610,
                        "comment": f"NX10_{tag[:14]}",
                        "type_time": mt5.ORDER_TIME_SPECIFIED,
                        "expiration": exp_ts,
                        "type_filling": get_filling_mode(sym_info),
                    })
                    last_bar_traded[sym] = bar_ts
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        order_id = int(res.order)
                        tracked_pending_tickets[order_id] = {"trigger": trig, "tag": tag, "score": score}
                        logging.info(f"[{sleeve_key}] PENDING {tag} {lots}L {sym} @ {trig} | SL={sl} TP={tp} (TTL {cfg['pending_ttl_mins']}m)")
                        log_intent(sleeve_key, sym, direction, lots, trig, sl, tp, score, "PLACED_PENDING", order_id)
                        send_nexus_tg(
                            f"🎯 <b>[NEXUS {sleeve_key} // PENDING BREAKOUT ARMED]</b>\n"
                            f"• Account: <code>#{cfg['login']}</code>\n"
                            f"• Asset: <b>{sym}</b> ({tag} {lots}L)\n"
                            f"• Trigger: <code>{trig}</code> | Ticket: <code>#{order_id}</code>\n"
                            f"• SL: <code>{sl}</code> | TP: <code>{tp}</code> ({cfg['rr_target']}R)\n"
                            f"• TTL: <b>{cfg['pending_ttl_mins']} mins</b> (Auto-OCO protected)"
                        )
                        break

            p_count = len([o for o in (mt5.orders_get() or []) if o.magic == 202610])
            status_str = f"ACTIVE_HYBRID (Open:{open_count} Pend:{p_count})" if cfg["enable_pending_breakout"] else f"ACTIVE_SCALP (Open:{open_count})"
            update_heartbeat(sleeve_key, cfg["login"], equity, open_count, status_str)
            time.sleep(3)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"[{sleeve_key}] Loop exception: {e}")
            time.sleep(5)

    mt5.shutdown()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python nexus_sleeve_worker.py <T1|T2|T3>")
        sys.exit(1)
    run_worker(sys.argv[1].upper())







