"""
QUANT-NEXUS TERMINAL 4 (T4) // EXACT 11/16/2026 LAPTOP MASTER ENGINE (#278060961) + TELEGRAM SENTINEL
- Account: Exness-MT5Trial5 #278071462 (C:\MT5_Sovereign_T4\terminal64.exe)
- Bot: @GODMODEAI2050_bot -> Chat ID 5279761713
- Assets: ["EURUSD", "BTCUSD", "XAUUSD", "GBPUSD", "USDJPY"]
- 15-Second Continuous Multi-Asset Scan Loop + M15 MA10 Imbalance Model + Spread*30/65 Geometry
- Exact Fingerprint: magic=999888, comment="Nexus Autonomous"
- Pillar 1 Asymmetric Invalidation Stacker + Auto-BE Lock + Closed Deal & Sentinel Telegram Cards
"""
import os
import sys
import time
import json
import sqlite3
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone
import numpy as np
import MetaTrader5 as mt5

T4_MT5_PATH = r"C:\MT5_Sovereign_T4\terminal64.exe"
LEDGER_DB = r"C:\Quant-Nexus-Eng\nexus_ledger.db"
STATE_FILE = r"C:\Quant-Nexus-Eng\t4_sovereign_state.json"
LOG_FILE = r"C:\Quant-Nexus-Eng\logs\t4_sovereign_apex.log"

TG_BOT_TOKEN = "8500432698:AAFLDz1nN_JeSMo2HBNx2gujV7tSlMfQGGg"
TG_CHAT_ID = 5279761713

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


def send_tg_message(text: str, parse_mode: str = "HTML") -> bool:
    """Thread-safe zero-dependency HTTPS Telegram dispatcher for @GODMODEAI2050_bot."""
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": str(TG_CHAT_ID),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as e:
        log.warning(f"Telegram send error: {e}")
        return False


def poll_tg_commands(scans: list, state: dict):
    """Lightweight non-blocking command handler (/status, /scan) for chat 5279761713."""
    try:
        offset = int(state.get("tg_update_offset", 0))
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates?timeout=0&limit=10"
        if offset > 0:
            url += f"&offset={offset}"
        with urllib.request.urlopen(url, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("ok"):
            return
        results = data.get("result", [])
        if not results:
            return
        max_uid = offset
        for upd in results:
            uid = int(upd.get("update_id", 0))
            if uid >= max_uid:
                max_uid = uid + 1
            msg = upd.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            txt = (msg.get("text") or "").strip().lower()
            if chat_id != TG_CHAT_ID or not txt:
                continue
            if txt.startswith("/status") or txt.startswith("/start"):
                acc = mt5.account_info()
                pos = list(mt5.positions_get() or [])
                lines = [
                    "?? <b>T4 SOVEREIGN NEXUS // LIVE TELEMETRY</b>",
                    "??????????????????????????",
                    f"? <b>Account:</b> <code>#278071462</code> (Exness-MT5Trial5)",
                    f"? <b>Balance:</b> <code>${acc.balance:,.2f}</code> | <b>Equity:</b> <code>${acc.equity:,.2f}</code>",
                    f"? <b>Free Margin:</b> <code>${acc.margin_free:,.2f}</code> | <b>Open:</b> <code>{len(pos)}/5</code>",
                ]
                if pos:
                    lines.append("??????????????????????????")
                    for p in pos:
                        side = "?? BUY" if p.type == 0 else "?? SELL"
                        lines.append(f"? <code>#{p.ticket}</code> <b>{p.symbol}</b> {side} <code>{p.volume:.2f}L</code> | <b>PnL:</b> <code>${p.profit:+.2f}</code>")
                    lines.append(f"
?? <b>Total Float:</b> <code>${sum(p.profit for p in pos):+.2f}</code>")
                send_tg_message("
".join(lines))
            elif txt.startswith("/scan"):
                lines = [
                    "?? <b>T4 OMEGA FX // 5-ASSET RADAR</b>",
                    "??????????????????????????",
                ]
                for idx, s in enumerate(scans, 1):
                    d_icon = "?? BUY" if s["direction"] == "BUY" else ("?? SELL" if s["direction"] == "SELL" else "? NEUTRAL")
                    badge = "? CLEARED ?72%" if s.get("cleared") else f"({s['edge']}%)"
                    lines.append(f"#{idx} <b>{s['symbol']}</b> | {d_icon} {badge} | @ <code>{s['price']}</code>")
                send_tg_message("
".join(lines))
        state["tg_update_offset"] = max_uid
        save_state(state)
    except Exception:
        pass


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"known_tickets": [], "be_locked_tickets": [], "tg_update_offset": 0}


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


def manage_breakeven_and_trailing(state: dict):
    """Protects open positions at Breakeven once +1.0R in profit and alerts Telegram."""
    be_locked = set(state.get("be_locked_tickets", []))
    dirty = False
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
                    if p.ticket not in be_locked:
                        be_locked.add(p.ticket)
                        dirty = True
                        send_tg_message(
                            f"??? <b>T4 AUTO-ARMOR // BREAKEVEN LOCKED</b>
"
                            f"??????????????????????????
"
                            f"? <b>Ticket:</b> <code>#{p.ticket}</code> (<b>{p.symbol}</b>)
"
                            f"? <b>Protected SL:</b> <code>{be_px}</code> (Zero-Risk)
"
                            f"? <b>Floating PnL:</b> <code>${p.profit:+.2f}</code>"
                        )
    if dirty:
        state["be_locked_tickets"] = list(be_locked)[-200:]
        save_state(state)


def check_closed_positions_and_notify(live_pos: list, state: dict):
    """Detects newly closed T4 positions and dispatches realized PnL cards to Telegram."""
    known = set(state.get("known_tickets", []))
    curr_tickets = {int(p.ticket) for p in live_pos}
    closed_tickets = known - curr_tickets

    if closed_tickets:
        now = datetime.now()
        start_ts = now.timestamp() - 86400
        deals = mt5.history_deals_get(start_ts, now.timestamp() + 3600) or []
        acc = mt5.account_info()
        eq_str = f"${acc.equity:,.2f}" if acc else "N/A"
        for t in closed_tickets:
            exit_deals = [d for d in deals if int(d.position_id) == t and d.entry == 1]
            if exit_deals:
                d = exit_deals[-1]
                net_pnl = float(d.profit + d.swap + d.commission)
                badge = "? TARGET / WIN" if net_pnl >= 0 else "?? STOP / EXIT"
                send_tg_message(
                    f"?? <b>T4 POSITION CLOSED // {badge}</b>
"
                    f"??????????????????????????
"
                    f"? <b>Ticket:</b> <code>#{t}</code> (<b>{d.symbol}</b>)
"
                    f"? <b>Realized PnL:</b> <code>${net_pnl:+.2f}</code>
"
                    f"? <b>Updated T4 Equity:</b> <code>{eq_str}</code>"
                )

    updated = list((known | curr_tickets) - closed_tickets)[-200:]
    if updated != state.get("known_tickets"):
        state["known_tickets"] = updated
        save_state(state)


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
    state = load_state()
    init_pos = list(mt5.positions_get() or [])
    if not state.get("known_tickets") and init_pos:
        state["known_tickets"] = [int(p.ticket) for p in init_pos]
        save_state(state)

    log.info(
        f"T4 NEXUS AUTONOMOUS (11/16/2026 + @GODMODEAI2050_bot) ONLINE | Account=#{acct.login} | "
        f"Equity=${acct.equity:.2f} | Open={len(init_pos)} | Cycle=15s"
    )
    send_tg_message(
        f"?? <b>T4 SOVEREIGN NEXUS // TELEGRAM TELEMETRY ONLINE</b>
"
        f"??????????????????????????
"
        f"? <b>Terminal:</b> <code>T4 (#278071462)</code> on AdmVps
"
        f"? <b>Engine:</b> <code>11/16/2026 Nexus Autonomous (Magic 999888)</code>
"
        f"? <b>Balance:</b> <code>${acct.balance:,.2f}</code> | <b>Equity:</b> <code>${acct.equity:,.2f}</code>
"
        f"? <b>Active Positions:</b> <code>{len(init_pos)}/5</code> (15s Multi-Asset Scan)
"
        f"? <b>Commands:</b> <code>/status</code> | <code>/scan</code>"
    )

    cycle_num = 0
    while True:
        try:
            acct = mt5.account_info()
            if not acct:
                time.sleep(3)
                continue

            manage_breakeven_and_trailing(state)

            scans = []
            for sym in ASSETS:
                res = calculate_asset_edge(sym)
                if res:
                    scans.append(res)
            scans.sort(key=lambda x: x.get("edge", 0), reverse=True)

            poll_tg_commands(scans, state)

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
                            send_tg_message(
                                f"???? <b>[T4 NEXUS SENTINEL: AUTO-FIRED TRADE]</b> ????
"
                                f"??????????????????????????
"
                                f"?? <b>Ticket:</b> <code>#{ticket}</code>
"
                                f"?? <b>Symbol:</b> <code>{sym}</code> ({direction} @ <code>{edge}%</code>)
"
                                f"?? <b>Sizing:</b> <code>{lots:.2f} Lots</code>
"
                                f"?? <b>SL:</b> <code>{sl}</code> | ?? <b>TP:</b> <code>{tp}</code>
"
                                f"??? <b>Status:</b> LIVE ON T4 (#278071462)"
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
                        send_tg_message(
                            f"?? <b>[T4 ASYMMETRIC STACK // PILLAR 1 ADD-ON]</b>
"
                            f"??????????????????????????
"
                            f"? <b>Stack Ticket:</b> <code>#{st_ticket}</code> (Parent <code>#{st_res['parent_ticket']}</code> @ <code>+{st_res['parent_r']}R</code> BE)
"
                            f"? <b>Symbol:</b> <code>{s_sym}</code> ({st_res['direction']} <code>{st_res['lot']:.2f}L</code>)
"
                            f"? <b>SL:</b> <code>{st_res['sl']}</code> | <b>TP:</b> <code>{st_res['tp']}</code>"
                        )

            live_pos = list(mt5.positions_get() or [])
            check_closed_positions_and_notify(live_pos, state)

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
