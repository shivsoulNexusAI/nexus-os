from micro_delta_imbalance import MicroDeltaImbalance
orderflow_profiler = MicroDeltaImbalance(tick_lookback=350, imbalance_threshold=0.20)
import time
import threading
import requests
import json
import MetaTrader5 as mt5
from quantum_delta_daemon import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    kelly_allocator, execute_order, get_atr, SYMBOLS
)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
STATE_FILE = "runtime_config.json"
MAX_GLOBAL_POSITIONS = 4

KEYBOARD = {
    "keyboard": [
        [{"text": "📊 /status"}, {"text": "📡 /scan"}],
        [{"text": "🎯 Gate 75%"}, {"text": "🎯 Gate 80%"}, {"text": "🚨 /flatten"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

def load_config():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"execution_edge_threshold": 0.75, "default_max_lot": 0.05, "basket_take_profit": 15.0}

def save_threshold(val: float):
    cfg = load_config()
    cfg["execution_edge_threshold"] = val
    with open(STATE_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def clamp_lot(symbol: str, raw_lot: float) -> float:
    cfg = load_config()
    max_caps = cfg.get("max_allowed_lots", {})
    cap = max_caps.get(symbol, cfg.get("default_max_lot", 0.05))
    return max(0.01, round(min(raw_lot, cap), 2))

def fmt_price(symbol: str, price: float) -> str:
    sinfo = mt5.symbol_info(symbol)
    digits = sinfo.digits if sinfo else (2 if "XAU" in symbol or "BTC" in symbol else 5)
    return f"{price:.{digits}f}"

def send_msg(text: str, markup=None):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup or KEYBOARD
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        r = requests.post(f"{BASE_URL}/sendMessage", json=payload, headers=headers, timeout=5)
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"Telegram send error: {e}")
        return None

def edit_msg(msg_id: int, text: str, markup=None):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": msg_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": markup
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        requests.post(f"{BASE_URL}/editMessageText", json=payload, headers=headers, timeout=4)
    except Exception:
        pass

def close_ticket(ticket, symbol, volume, order_type):
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False
    close_type = mt5.ORDER_TYPE_SELL if order_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if order_type == mt5.ORDER_TYPE_BUY else tick.ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 30
    }
    res = mt5.order_send(req)
    return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

def get_live_scan():
    if not mt5.terminal_info():
        mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe")

    cands = []
    for sym in SYMBOLS:
        atr = get_atr(sym)
        if atr <= 0:
            continue
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 12)
        if rates is not None and len(rates) >= 10:
            delta = rates[-1]['close'] - rates[-5]['close']
            direction = "BUY" if delta > 0 else "SELL"
            spread_ratio = abs(delta) / atr if atr > 0 else 0.5
            edge = round(min(0.825, max(0.680, 0.720 + (spread_ratio * 0.035))), 3)
        else:
            direction, edge = "BUY", 0.720
        cands.append({"symbol": sym, "direction": direction, "edge": edge, "atr": atr})
    cands.sort(key=lambda x: x["edge"], reverse=True)
    return cands

def build_pnl_dashboard():
    if not mt5.terminal_info():
        mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe")

    acc = mt5.account_info()
    positions = mt5.positions_get() or []
    cfg = load_config()
    gate = cfg.get("execution_edge_threshold", 0.75)
    basket_tp = cfg.get("basket_take_profit", 15.0)

    if not positions:
        text = (
            "📊 <b>[NEXUS COCKPIT STATUS: CLEAN BOOK]</b>\n"
            f"• Balance : <code>${acc.balance:.2f}</code>\n"
            f"• Equity  : <code>${acc.equity:.2f}</code>\n"
            f"• Margin  : <code>${acc.margin_free:.2f}</code>\n"
            "• Active  : <b>0 Positions (100% Cash)</b>\n"
            f"• Gate    : <b>{gate*100:.1f}%</b> | Auto-TP: <b>+${basket_tp:.2f}</b>"
        )
        return text, None, 0.0

    total_pnl = sum(p.profit for p in positions)
    pnl_sign = "+" if total_pnl >= 0 else ""
    gauge = "🟢 <b>NET PROFITABLE</b>" if total_pnl >= 0 else "🔴 <b>FLOATING DRAWDOWN</b>"

    win_count = sum(1 for p in positions if p.profit > 0)
    loss_count = sum(1 for p in positions if p.profit < 0)

    lines = [
        "🏛️ <b>[QUANT NEXUS OMEGA APEX PNL COCKPIT]</b>",
        f"Status: {gauge}",
        f"<b>Net Floating PnL : <code>{pnl_sign}${total_pnl:.2f} USD</code></b>",
        f"<b>Equity :</b> <code>${acc.equity:.2f}</code> | <b>Balance :</b> <code>${acc.balance:.2f}</code>",
        f"<b>Deals  :</b> <b>{len(positions)}/{MAX_GLOBAL_POSITIONS} Slots</b> (🟢 {win_count} Win | 🔴 {loss_count} Loss)",
        f"<b>Target :</b> Auto-Harvest @ <b>+${basket_tp:.2f} USD</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📋 <b>ACTIVE POSITION LEDGER:</b>"
    ]

    for p in positions:
        p_type = "BUY" if p.type == 0 else "SELL"
        p_sign = "+" if p.profit >= 0 else ""
        icon = "🟢" if p.profit >= 0 else "🔴"
        open_p = fmt_price(p.symbol, p.price_open)
        curr_p = fmt_price(p.symbol, p.price_current)
        lines.append(
            f"{icon} <code>#{p.ticket}</code> <b>{p.symbol}</b> {p_type} {p.volume}L\n"
            f"   └ In: {open_p} → Now: {curr_p} | <b>{p_sign}${p.profit:.2f}</b>"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")

    inline_buttons = [
        [
            {"text": f"🚨 FLATTEN BOOK ({pnl_sign}${total_pnl:.2f})", "callback_data": "CONFIRM_FLATTEN"}
        ],
        [
            {"text": f"💰 HARVEST {win_count} WINNERS", "callback_data": "HARVEST_WINNERS"},
            {"text": "🔄 REFRESH PNL", "callback_data": "REFRESH_PNL"}
        ]
    ]

    return "\n".join(lines), {"inline_keyboard": inline_buttons}, total_pnl

def build_radar_report(source="MANUAL"):
    cands = get_live_scan()
    cfg = load_config()
    gate = cfg.get("execution_edge_threshold", 0.75)
    acc = mt5.account_info()
    positions = mt5.positions_get() or []
    open_symbols = {p.symbol: p for p in positions}

    header_tag = "📡 [AUTO-SCAN 60S PULSE]" if source == "AUTO" else "🏛️ [QUANT NEXUS OMEGA APEX RADAR]"
    lines = [
        f"<b>{header_tag}</b>",
        f"<b>Auto-Gate:</b> <code>{gate*100:.1f}%</code> | <b>Exposure:</b> <code>{len(positions)}/{MAX_GLOBAL_POSITIONS}</code> | <b>Equity:</b> <code>${acc.equity:.2f}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🎯 <b>MARKET MOMENTUM & SETUPS:</b>"
    ]

    inline_buttons = []
    slots_full = len(positions) >= MAX_GLOBAL_POSITIONS

    for c in cands:
        sym = c['symbol']
        score = c['edge'] * 100
        raw_lot = kelly_allocator.calculate_lot_size(sym, acc.equity, c['edge'], 2.0)
        safe_lot = clamp_lot(sym, raw_lot)

        if sym in open_symbols:
            lines.append(f"✅ <code>{sym:<7}</code> | <b>{c['direction']}</b> @ <b>{score:.1f}%</b> [RUNNING]")
        elif slots_full:
            lines.append(f"🔒 <code>{sym:<7}</code> | <b>{c['direction']}</b> @ <b>{score:.1f}%</b> [MAX CAPACITY]")
        else:
            tag = "🔥" if score >= gate * 100 else ("⚡" if score >= 73.5 else "💤")
            lines.append(f"{tag} <code>{sym:<7}</code> | <b>{c['direction']}</b> @ <b>{score:.1f}%</b> ({safe_lot}L)")
            
            if score >= 73.5:
                inline_buttons.append([
                    {"text": f"⚡ FIRE {sym} {c['direction']} ({safe_lot}L)", "callback_data": f"FIRE_{c['direction']}_{sym}"}
                ])

    if inline_buttons:
        inline_buttons.append([{"text": "❌ DISMISS", "callback_data": "DISMISS"}])

    return "\n".join(lines), {"inline_keyboard": inline_buttons} if inline_buttons else None

def evaluate_and_auto_trigger():
    if not mt5.terminal_info():
        mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe")

    positions = mt5.positions_get() or []
    cfg = load_config()
    gate = cfg.get("execution_edge_threshold", 0.75)
    cands = get_live_scan()
    open_symbols = {p.symbol for p in positions}
    acc = mt5.account_info()

    # 1. Autonomous Execution
    if len(positions) < MAX_GLOBAL_POSITIONS:
        for c in cands:
            sym = c["symbol"]
            if c["edge"] >= gate and sym not in open_symbols:
                atr = c["atr"]
                sl_dist = atr * 1.5
                tp_dist = atr * 3.0
                raw_lot = kelly_allocator.calculate_lot_size(sym, acc.equity, c["edge"], 2.0)
                safe_lot = clamp_lot(sym, raw_lot)
                direction = c["direction"]

                print(f"[{time.strftime('%H:%M:%S')}] >>> AUTO-TRIGGER EXECUTED: {sym} {direction} {safe_lot}L (Edge: {c['edge']*100:.1f}%)")
                send_msg(
                    f"⚡ <b>[AUTO-TRIGGER FIRED]</b> Edge <b>{c['edge']*100:.1f}%</b> &ge; Gate {gate*100:.1f}%\n"
                    f"• Symbol    : <code>{sym}</code> {direction}\n"
                    f"• Allocation: <code>{safe_lot}L</code> (Quarter-Kelly)\n"
                    f"• Capacity  : <b>{len(positions)+1}/{MAX_GLOBAL_POSITIONS} Slots</b>"
                )
                success = execute_order(sym, direction, safe_lot, sl_dist, tp_dist)
                if success:
                    open_symbols.add(sym)
                    time.sleep(1)
                    break

    # 2. Autonomous Setup Broadcaster (Pushes to Telegram on Edge Events or Setup Shifts)
    high_setups = [c for c in cands if c["edge"] >= 0.735 and c["symbol"] not in open_symbols]
    if high_setups and len(positions) < MAX_GLOBAL_POSITIONS:
        radar_text, radar_markup = build_radar_report(source="AUTO")
        send_msg(radar_text, markup=radar_markup)
        print(f"[{time.strftime('%H:%M:%S')}] [Broadcast] Dispatched High-Edge Setup Card to Telegram.")

def check_basket_auto_harvest():
    positions = mt5.positions_get() or []
    if not positions:
        return
    cfg = load_config()
    target_tp = cfg.get("basket_take_profit", 15.0)
    total_pnl = sum(p.profit for p in positions)

    if total_pnl >= target_tp:
        print(f"[{time.strftime('%H:%M:%S')}] >>> AUTO-HARVEST HIT (+${total_pnl:.2f}) - Liquidating...")
        send_msg(
            f"🎯 <b>[AUTO-HARVEST TRIGGERED]</b> Net Basket Profit <b>+${total_pnl:.2f}</b> hit target <b>+${target_tp:.2f}</b>!\n"
            f"Liquidating all {len(positions)} positions to bank profit..."
        )
        for p in positions:
            close_ticket(p.ticket, p.symbol, p.volume, p.type)
        send_msg("🛡️ <b>[PROFIT BANKED]</b> Book flattened to 100% Cash Reserves.")

def autonomous_scanner_daemon():
    print("[+] Dedicated 60-Second Autonomous Pulse Thread Activated.")
    scan_counter = 0

    while True:
        try:
            check_basket_auto_harvest()
            scan_counter += 5
            if scan_counter >= 60:
                scan_counter = 0
                now_str = time.strftime('%H:%M:%S')
                print(f"[{now_str}] [*] Autonomous 60s Pulse Running...")
                evaluate_and_auto_trigger()
        except Exception as e:
            print(f"[-] Autonomous thread error: {e}")

        time.sleep(5)

def main():
    if not mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe"):
        print("[-] MT5 Init Failed")
        return

    requests.get(f"{BASE_URL}/getUpdates?offset=-1", timeout=5)
    cfg = load_config()
    gate = cfg.get("execution_edge_threshold", 0.75)
    basket_tp = cfg.get("basket_take_profit", 15.0)

    # Start Autonomous Thread
    scanner_thread = threading.Thread(target=autonomous_scanner_daemon, daemon=True)
    scanner_thread.start()

    send_msg(
        "🏛️ <b>[QUANT NEXUS OMEGA APEX BROADCASTER ONLINE]</b>\n"
        f"• Auto-Gate Threshold : <b>{gate*100:.1f}%</b>\n"
        f"• Max Portfolio Slots : <b>{MAX_GLOBAL_POSITIONS} Slots</b>\n"
        "• Autonomous Cadence  : <b>Exact 60-Second Broadcast + Fire</b>\n"
        f"• Basket Harvest Gate : <b>+${basket_tp:.2f} USD</b>"
    )

    offset = None

    while True:
        try:
            url = f"{BASE_URL}/getUpdates?timeout=2"
            if offset:
                url += f"&offset={offset}"
            res = requests.get(url, timeout=4).json()
            updates = res.get("result", [])

            for u in updates:
                offset = u["update_id"] + 1

                if "callback_query" in u:
                    cb = u["callback_query"]
                    data = cb.get("data", "")
                    cb_id = cb.get("id")
                    msg_obj = cb.get("message", {})
                    msg_id = msg_obj.get("message_id")

                    if data == "REFRESH_PNL":
                        pnl_text, pnl_markup, _ = build_pnl_dashboard()
                        if msg_id:
                            edit_msg(msg_id, pnl_text, pnl_markup)
                        else:
                            send_msg(pnl_text, markup=pnl_markup)
                        requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "PnL Updated."})

                    elif data == "HARVEST_WINNERS":
                        positions = mt5.positions_get() or []
                        winners = [p for p in positions if p.profit > 0]
                        harvested_pnl = 0.0
                        closed_count = 0
                        for p in winners:
                            if close_ticket(p.ticket, p.symbol, p.volume, p.type):
                                harvested_pnl += p.profit
                                closed_count += 1
                        send_msg(f"💰 <b>[PROFIT HARVESTED]</b> Banked {closed_count} winner(s) | Net: <b>+${harvested_pnl:.2f} USD</b>")
                        requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": f"Banked +${harvested_pnl:.2f}!"})

                    elif data in ["CONFIRM_FLATTEN", "FLATTEN"]:
                        positions = mt5.positions_get() or []
                        for p in positions:
                            close_ticket(p.ticket, p.symbol, p.volume, p.type)
                        send_msg(f"🚨 <b>[PORTFOLIO FLATTENED]</b> Closed all {len(positions)} positions. Book 100% Cash.")
                        requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "All trades closed."})

                    elif data.startswith("FIRE_"):
                        _, direction, sym = data.split("_")
                        positions = mt5.positions_get() or []
                        
                        if any(p.symbol == sym for p in positions):
                            send_msg(f"⚠️ <b>[VETO]</b> {sym} already active.")
                            requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "Already open."})
                            continue

                        if len(positions) >= MAX_GLOBAL_POSITIONS:
                            send_msg(f"⚠️ <b>[VETO]</b> Portfolio capacity ({MAX_GLOBAL_POSITIONS}) reached.")
                            requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "Max capacity."})
                            continue

                        atr = get_atr(sym)
                        sl_dist = atr * 1.5
                        tp_dist = atr * 3.0
                        acc = mt5.account_info()
                        raw_lot = kelly_allocator.calculate_lot_size(sym, acc.equity, 0.80, 2.0)
                        safe_lot = clamp_lot(sym, raw_lot)

                        send_msg(f"⚡ <b>[AUTHORIZED]</b> Firing {sym} {direction} {safe_lot}L...")
                        success = execute_order(sym, direction, safe_lot, sl_dist, tp_dist)
                        ans = "Executed in MT5" if success else "Broker Rejected"
                        requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": ans})

                    elif data == "DISMISS":
                        requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "Dismissed."})

                elif "message" in u and "text" in u["message"]:
                    cmd = u["message"]["text"].strip()

                    if cmd in ["/status", "📊 /status"]:
                        pnl_text, pnl_markup, _ = build_pnl_dashboard()
                        send_msg(pnl_text, markup=pnl_markup)

                    elif cmd in ["/scan", "📡 /scan"]:
                        radar_text, radar_markup = build_radar_report(source="MANUAL")
                        send_msg(radar_text, markup=radar_markup)

                    elif cmd in ["🎯 Gate 75%", "/gate 75"]:
                        save_threshold(0.75)
                        send_msg("✅ <b>Trigger Gate updated to 75.0%</b>")

                    elif cmd in ["🎯 Gate 80%", "/gate 80"]:
                        save_threshold(0.80)
                        send_msg("✅ <b>Trigger Gate updated to 80.0%</b> (Apex Mode)")

                    elif cmd in ["/flatten", "🚨 /flatten"]:
                        positions = mt5.positions_get() or []
                        if not positions:
                            send_msg("🛡️ <b>Clean Book:</b> No open positions.")
                        else:
                            for p in positions:
                                close_ticket(p.ticket, p.symbol, p.volume, p.type)
                            send_msg(f"🚨 <b>[FLATTENED]</b> Closed {len(positions)} position(s). Book is 100% Cash.")

        except Exception as e:
            time.sleep(1)

        time.sleep(0.5)

if __name__ == "__main__":
    main()
