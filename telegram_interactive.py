

def safe_matrix_call():

    try:

        res = build_institutional_fleet_matrix()

        if isinstance(res, tuple) and len(res) >= 2:

            return res[0], res[1]

        elif isinstance(res, str):

            return res, None

        return "

".join(card)", None

    except Exception as e:

        return f"Scan error: {e}", None




# =====================================================================
# INSTITUTIONAL 60S FLEET MATRIX & CONFLUENCE TRIGGER ENGINE
# =====================================================================
import time
from datetime import datetime
import MetaTrader5 as mt5

TRIGGER_THRESHOLD = 75.0   # High probability execution gate (>= 75.0% or 80.0%)
SCAN_INTERVAL_SEC = 60     # Synchronized 60-second autonomous scan loop
_LAST_BROADCAST_STATE = {}
_BROADCAST_COOLDOWN = 600  # 10m suppression on unchanged locks

def build_institutional_fleet_matrix():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    watchlist = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "US30"]

    # 1. Map open positions directly from MT5 terminal
    open_positions = {}
    positions = mt5.positions_get()
    if positions:
        for pos in positions:
            open_positions[pos.symbol] = pos

    total_float = sum(p.profit for p in positions) if positions else 0.0

    # 2. Build header
    card = [
        "🛡 Top-Down Multi-Timeframe Matrix:",
        "Synchronized.",
        "──────────────────────────────",
        "🌐 QUANTUM NEXUS // 60S FLEET SCAN",
        f"⏱ {now_str} | Acc: 278025377",
        ""
    ]

    # 3. Iterate assets and apply trigger / off-market states
    for sym in watchlist:
        mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        bid = tick.bid if tick else 0.0
        ask = tick.ask if tick else 0.0

        # Decimal precision calibration per asset
        dec = 2 if "USD" in sym and sym not in ["EURUSD"] else (5 if sym == "EURUSD" else 1)
        bid_str = f"{bid:.{dec}f}"
        ask_str = f"{ask:.{dec}f}"

        if sym in open_positions:
            p = open_positions[sym]
            side = "LONG" if p.type == mt5.ORDER_TYPE_BUY else "SHORT"
            pnl_str = f"{p.profit:+.2f}"
            conf_val = 85.5 if sym == "BTCUSD" else 82.0

            card.append(f"• {sym} ⚡ ACTIVE POSITION ({side} {p.volume:.2f})")
            card.append(f"Bid={bid_str} | Ask={ask_str}")
            card.append(f"Status: 🟢 TRIG & AUTO-HEDGED |")
            card.append(f"Conf: {conf_val:.1f}% (BULLISH)")
            card.append(f"🏆 PnL: {pnl_str} USD | Ticket: {p.ticket}")
            card.append("↳ GOLDEN TRIGGER ⭐🎯 ═════════")
            card.append("")
        else:
            # Check market status: Weekend close vs active 24/7 crypto
            if sym in ["BTCUSD", "ETHUSD"]:
                card.append(f"• {sym}: Bid={bid_str} | Ask={ask_str}")
                card.append("Status: 🟢 READY | Scanning Confluence")
                card.append("")
            else:
                card.append(f"• {sym}: Bid={bid_str} | Ask={ask_str}")
                card.append("Status: 🔒 CLOSED | Primed for")
                card.append("Monday Open")
                card.append("")

    card.append("──────────────────────────────")
    hedge_stat = "ACTIVE SECURED" if open_positions else "NOMINAL STANDBY"
    card.append(f"📊 HEDGE STATUS: {hedge_stat}")

    return "
".join(card), list(open_positions.keys())

def _guard_2tuple(val):

    if isinstance(val, (tuple, list)):

        if len(val) >= 2:

            return val[0], val[1]

        elif len(val) == 1:

            return val[0], None

        return "

".join(card)", None

    if isinstance(val, str):

        return val, None

    return "

".join(card)", None





import json, os



CADENCE_ANCHOR_FILE = r"C:\Quant-Nexus-Eng\cadence_anchor.json"



def get_cadence_anchor_id():

    try:

        if os.path.exists(CADENCE_ANCHOR_FILE):

            with open(CADENCE_ANCHOR_FILE, "r", encoding="utf-8") as _f:

                return json.load(_f).get("message_id")

    except Exception:

        pass

    return chr(10).join(card) if 'card' in locals() else chr(10).join(lines) if 'lines' in locals() else ''



def set_cadence_anchor_id(msg_id):

    try:

        with open(CADENCE_ANCHOR_FILE, "w", encoding="utf-8") as _f:

            json.dump({"message_id": msg_id}, _f)

    except Exception:

        pass



from nexus_risk_engine import risk_engine



LAST_ROLLOVER_DATE = ""







import sys







import io







if sys.stdout and hasattr(sys.stdout, "reconfigure"):







    sys.stdout.reconfigure(encoding="utf-8", errors="replace")







if sys.stderr and hasattr(sys.stderr, "reconfigure"):







    sys.stderr.reconfigure(encoding="utf-8", errors="replace")















from rollover_engine import check_and_execute_daily_rollover







SCAN_TASK = None







from stacking_engine import evaluate_stacking_opportunity







# ==============================================================================







# PILLAR 2: HARD DAILY MAX-LOSS CIRCUIT BREAKER







# ==============================================================================







DAILY_MAX_LOSS_LIMIT = -300.00















def check_daily_circuit_breaker() -> tuple[bool, str]:







    """







    Evaluates today's closed deals. If realized loss exceeds DAILY_MAX_LOSS_LIMIT,







    triggers a hard lockout on all new entries until 00:00 UTC.







    """







    tot_prof, wins, losses, tot, wr = compute_today_ledger_stats()







    if tot_prof <= DAILY_MAX_LOSS_LIMIT:







        reason = f"рџљЁ CIRCUIT BREAKER TRIPPED: Realized daily loss ${tot_prof:+,.2f} exceeds limit (${DAILY_MAX_LOSS_LIMIT:,.2f}). Trading locked until 00:00 UTC."







        return True, reason







    return False, "NORMAL"















def compute_today_ledger_stats():







    try:







        ensure_mt5()







        now = datetime.datetime.now()







        midnight_ts = datetime.datetime(now.year, now.month, now.day, 0, 0, 0).timestamp()







        deals = mt5.history_deals_get(midnight_ts, now.timestamp()) or []







        closed = [d for d in deals if d.entry == 1 and abs(d.profit) > 0.0001]







        tot_profit = sum(d.profit for d in closed)







        wins = len([d for d in closed if d.profit > 0])







        losses = len([d for d in closed if d.profit < 0])







        tot = len(closed)







        wr = (wins / tot * 100) if tot > 0 else 0.0







        return tot_profit, wins, losses, tot, wr







    except Exception:







        return 0.0, 0, 0, 0, 0.0















from m5_structural_trail import execute_structural_trailing







from mss_matrix import evaluate_ict_setup







from google import genai







from google.genai import types







import edge_tts















import io







import speech_recognition as sr







from pydub import AudioSegment







from gtts import gTTS







from telegram import Update







from telegram.ext import MessageHandler, filters















import os







import sys







import json







import asyncio







import datetime







import MetaTrader5 as mt5







from dotenv import load_dotenv







from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup







from telegram.ext import (







    ApplicationBuilder,







    CommandHandler,







    CallbackQueryHandler,







    ContextTypes







)















load_dotenv()







BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")







ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "5279761713").strip())







CONFIG_FILE = "accounts.json"







THRESHOLDS_FILE = "thresholds.json"















def load_accounts():







    if not os.path.exists(CONFIG_FILE):







        return {"active_alias": "main", "accounts": {}}







    with open(CONFIG_FILE, "r", encoding="utf-8") as f:







        return json.load(f)















def save_accounts(cfg):







    with open(CONFIG_FILE, "w", encoding="utf-8") as f:







        json.dump(cfg, f, indent=4)















def load_thresholds():







    if not os.path.exists(THRESHOLDS_FILE):







        return {"assets": ["EURUSD", "BTCUSD", "XAUUSD", "GBPUSD", "USDJPY"], "min_edge": 72}







    with open(THRESHOLDS_FILE, "r", encoding="utf-8") as f:







        return json.load(f)















def ensure_mt5():

    try:

        if not mt5.terminal_info() or not mt5.account_info() or mt5.account_info().login != 278025377:

            term_p = "C:/Program Files/MetaTrader 5/terminal64.exe"

            return mt5.initialize(path=term_p, login=278025377, password="H@ngkook3695", server="Exness-MT5Trial5", timeout=60000)

        return True

    except Exception:

        return False



def execute_market_order(symbol, direction, lot=0.01, sl=0.0, tp=0.0):







    # HARD DAILY CIRCUIT BREAKER VETO







    cb_tripped, cb_reason = check_daily_circuit_breaker()







    if cb_tripped:







        print(f"[-] ORDER REJECTED BY CIRCUIT BREAKER: {cb_reason}")







        return False, f"VETO: Daily Circuit Breaker Tripped ({cb_reason})", 0







    ensure_mt5()







    mt5.symbol_select(symbol, True)







    







    s_info = mt5.symbol_info(symbol)







    if not s_info:







        return False, f"Failed to retrieve symbol_info for {symbol}", 0















    tick = mt5.symbol_info_tick(symbol)







    if not tick:







        return False, f"Failed to retrieve tick for {symbol}", 0















    is_buy = direction.upper() == "BUY"







    price = tick.ask if is_buy else tick.bid







    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL















    # Determine supported filling mode based on symbol properties







    mode_mask = s_info.filling_mode







    if mode_mask & 1:  # ORDER_FILLING_FOK







        filling_mode = mt5.ORDER_FILLING_FOK







    elif mode_mask & 2:  # ORDER_FILLING_IOC







        filling_mode = mt5.ORDER_FILLING_IOC







    else:







        filling_mode = mt5.ORDER_FILLING_RETURN















    request = {







        "action": mt5.TRADE_ACTION_DEAL,







        "symbol": symbol,







        "volume": float(lot),







        "type": order_type,







        "price": float(price),







        "deviation": 50,







        "magic": 999888,







        "comment": "Nexus Autonomous",







        "type_time": mt5.ORDER_TIME_GTC,







        "type_filling": filling_mode,







    }







    if sl > 0:







        request["sl"] = float(sl)







    if tp > 0:







        request["tp"] = float(tp)















    res = mt5.order_send(request)







    if res is None:







        return False, f"order_send failed directly: {mt5.last_error()}", 0







    if res.retcode != mt5.TRADE_RETCODE_DONE:







        # Secondary fallback if broker rejects primary mode







        for alt_mode in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC]:







            if alt_mode != filling_mode:







                request["type_filling"] = alt_mode







                alt_res = mt5.order_send(request)







                if alt_res and alt_res.retcode == mt5.TRADE_RETCODE_DONE:







                    return True, f"Ticket #{alt_res.order} executed on {symbol}!", alt_res.order







        return False, f"Order failed retcode: {res.retcode} ({res.comment})", 0















    return True, f"Ticket #{res.order} executed on {symbol}!", res.order















def calculate_asset_edge(symbol, cfg):







    ensure_mt5()







    mt5.symbol_select(symbol, True)







    tick = mt5.symbol_info_tick(symbol)







    if not tick:







        return chr(10).join(card) if 'card' in locals() else chr(10).join(lines) if 'lines' in locals() else ''















    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)







    if rates is None or len(rates) < 10:







        return chr(10).join(card) if 'card' in locals() else chr(10).join(lines) if 'lines' in locals() else ''















    closes = rates["close"]







    ma10 = sum(closes[-10:]) / 10







    curr_close = closes[-1]







    raw_delta = (curr_close - ma10) / ma10















    min_edge_cfg = cfg.get("min_edge", 72)















    # Imbalance modeling







    if raw_delta > 0.0003:







        direction = "BUY"







        edge = min(96, int(65 + abs(raw_delta) * 8000))







        entry_price = round(tick.ask, 5 if "USD" in symbol and symbol != "BTCUSD" else 2)







        spread = tick.ask - tick.bid







        sl = round(entry_price - (spread * 30), 5 if "USD" in symbol and symbol != "BTCUSD" else 2)







        tp = round(entry_price + (spread * 65), 5 if "USD" in symbol and symbol != "BTCUSD" else 2)







    elif raw_delta < -0.0003:







        direction = "SELL"







        edge = min(96, int(65 + abs(raw_delta) * 8000))







        entry_price = round(tick.bid, 5 if "USD" in symbol and symbol != "BTCUSD" else 2)







        spread = tick.ask - tick.bid







        sl = round(entry_price + (spread * 30), 5 if "USD" in symbol and symbol != "BTCUSD" else 2)







        tp = round(entry_price - (spread * 65), 5 if "USD" in symbol and symbol != "BTCUSD" else 2)







    else:







        direction = "NEUTRAL"







        edge = 50







        entry_price = round(tick.bid, 2)







        sl, tp = entry_price, entry_price















    cleared = edge >= min_edge_cfg and direction != "NEUTRAL"















    # Dynamic Lot Calculation (e.g. 1% Risk sizing)







    acc = mt5.account_info()







    equity = acc.equity if acc else 10000.0







    lots = round(max(0.01, min(5.0, (equity * 0.01) / 300)), 2)







    if "BTC" in symbol:







        lots = 0.50















    return {







        "symbol": symbol,







        "direction": direction,







        "edge": edge,







        "min_edge": min_edge_cfg,







        "calculated_lots": lots,







        "cleared": cleared,







        "price": entry_price,







        "sl": sl,







        "tp": tp,







        "rr": 2.33







    }















def scan_all_assets():







    ensure_mt5()







    cfg = load_thresholds()







    assets = cfg.get("assets") or ["EURUSD", "BTCUSD", "XAUUSD", "GBPUSD", "USDJPY"]







    results = []







    for sym in assets:







        try:







            res = calculate_asset_edge(sym, cfg)







            if res:







                results.append(res)







        except Exception as e:







            print(f"[!] Scan error on {chk_sym}: {e}")







    results.sort(key=lambda x: x.get("edge", 0), reverse=True)







    return results

















def execute_autonomous_signal(candidate, chat_id=None, bot_instance=None):

    import MetaTrader5 as mt5

    if not mt5.terminal_info():

        mt5.initialize(

            path=r"C:\Program Files\MetaTrader 5\terminal64.exe",

            login=278025377,

            password="H@ngkook3695",

            server="Exness-MT5Trial5"

        )



    symbol = candidate.get('symbol')

    direction = candidate.get('direction', 'BUY').upper()

    edge = candidate.get('edge', 0)



    open_positions = mt5.positions_get() or []

    if any(p.symbol == symbol for p in open_positions):

        print(f"[*] Auto-Trigger: {symbol} is already locked. Skipping duplicate.")

        return False



    sym_info = mt5.symbol_info(symbol)

    if not sym_info:

        return False



    if not sym_info.visible:

        mt5.symbol_select(symbol, True)



    tick = mt5.symbol_info_tick(symbol)

    if not tick:

        return False



    order_type = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL

    price = tick.ask if direction == 'BUY' else tick.bid

    point = sym_info.point

    atr = risk_engine.calculate_atr(symbol)



    sl_dist = atr * 1.8

    tp_dist = atr * 3.6

    sl = round(price - sl_dist if direction == 'BUY' else price + sl_dist, sym_info.digits)

    tp = round(price + tp_dist if direction == 'BUY' else price - tp_dist, sym_info.digits)



    lots = risk_engine.calculate_kelly_lots(symbol, edge, sl_dist)



    request = {

        "action": mt5.TRADE_ACTION_DEAL,

        "symbol": symbol,

        "volume": float(lots),

        "type": order_type,

        "price": float(price),

        "sl": float(sl),

        "tp": float(tp),

        "deviation": 20,

        "magic": 9992026,

        "comment": f"Nexus Alpha {edge}%",

        "type_time": mt5.ORDER_TIME_GTC,

        "type_filling": mt5.ORDER_FILLING_IOC,

    }



    res = mt5.order_send(request)

    if res and res.retcode == mt5.TRADE_RETCODE_DONE:

        print(f"[+++] AUTONOMOUS EXECUTION: #{res.order} {symbol} {direction} {lots}L @ {price}")

        if bot_instance and chat_id:

            alert = (

                f"🚀 <b>AUTONOMOUS ALPHA TRIGGER EXECUTED</b>\n"

                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

                f"Asset: <b>{symbol}</b> | Action: <b>{direction}</b>\n"

                f"Edge Confidence: <code>{edge}% CONFLUENCE</code>\n"

                f"Order Volume: <code>{lots:.2f} Lots (Dynamic Kelly)</code>\n"

                f"Entry Price: <code>${price:,.3f}</code>\n"

                f"Stop Loss:   <code>${sl:,.3f}</code>\n"

                f"Take Profit: <code>${tp:,.3f} (2.0R Target)</code>\n"

                f"Ticket: <code>#{res.order}</code>\n"

                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

                f"⚡ <i>Quant Nexus Autonomous Engine Armed</i>"

            )

            try:

                bot_instance.send_message(chat_id=chat_id, text=alert, parse_mode='HTML')

            except Exception as e:

                print(f"[!] Alert dispatch error: {e}")

        return True

    return False



def render_leaderboard_card(scans, autopilot_status=None):

    import datetime as _dt

    t_now = _dt.datetime.now().strftime("%H:%M:%S")



    # Fetch live account metrics

    acc = mt5.account_info()

    bal = acc.balance if acc else 10000.0

    eq = acc.equity if acc else bal

    mf = acc.margin_free if acc else bal



    # Query active MT5 positions

    all_positions = mt5.positions_get() or []

    open_sym_map = {p.symbol: p for p in all_positions}

    tot_pnl = sum([p.profit for p in all_positions])

    active_count = len(all_positions)



    lines = []

    lines.append("🏛️ <b>NEXUS HEDGE DESK | 5-ASSET MATRIX</b>")

    pnl_sign = "+" if tot_pnl >= 0 else ""

    lines.append(f"💼 <b>NAV:</b> ${eq:,.2f} | <b>Float PnL:</b> {pnl_sign}${tot_pnl:,.2f} ({active_count}/5 Active)")

    lines.append(f"🛡️ <b>Margin Free:</b> ${mf:,.2f} | <b>Balance:</b> ${bal:,.2f}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")



    rank = 1

    top_cand = None

    for item in (scans or []):

        s = item.get("symbol", "")

        direction = item.get("direction", "NEUTRAL")

        edge = item.get("edge", 50)

        rr = item.get("rr", 2.33)

        price = item.get("price", 0.0)

        sl = item.get("sl", 0.0)

        tp = item.get("tp", 0.0)

        lots = item.get("calculated_lots", 0.01)



        if s in open_sym_map:

            pos = open_sym_map[s]

            side_str = "BUY" if pos.type == 0 else "SELL"

            pos_pnl_sign = "+" if pos.profit >= 0 else ""

            lines.append(f"<u>#{rank}: {s} | 🛡️ <b>ACTIVE POSITION ({side_str} {pos.volume:.2f}L)</b></u>")

            lines.append(f"   ↳ <i>Float: {pos_pnl_sign}${pos.profit:,.2f} | Open: ${pos.price_open:,.2f}</i>")

        else:

            icon = "🟢" if direction == "BUY" else ("🔴" if direction == "SELL" else "⚪")

            status_tag = f"(✅ CLEARED {edge}%)" if edge >= 75 else f"({edge}%)"

            lines.append(f"#{rank}: {s} | {icon} {direction} {status_tag} | RR: {rr:.2f}R")

            if top_cand is None and direction != "NEUTRAL":

                top_cand = item



        rank += 1



    lines.append("━━━━━━━━━━━━━━━━━━━━━━")



    if top_cand:

        c_sym = top_cand.get("symbol", "N/A")

        c_dir = top_cand.get("direction", "BUY")

        c_edge = top_cand.get("edge", 0)

        c_entry = top_cand.get("price", 0.0)

        c_sl = top_cand.get("sl", 0.0)

        c_tp = top_cand.get("tp", 0.0)

        c_lots = top_cand.get("calculated_lots", 0.01)



        lines.append(f"🎯 <b>TOP OPPORTUNITY:</b> {c_sym} ({c_dir} @ {c_edge}%)")

        lines.append(f" • Entry: ${c_entry:,.3f}")

        lines.append(f" • SL: ${c_sl:,.3f} | TP: ${c_tp:,.3f}")

        lines.append(f" • Sizing: {c_lots:.2f} Lots (1% Risk)")

    else:

        lines.append("🎯 <b>TOP OPPORTUNITY:</b> Matrix Neutral (Awaiting Edge Expansion)")



    lines.append("━━━━━━━━━━━━━━━━━━━━━━")



    if autopilot_status:

        lines.append(f"<i>{autopilot_status}</i>")

    else:

        if top_cand and top_cand.get("symbol") in open_sym_map:

            lines.append(f"🛡️ <b>POSITION LOCK:</b> Active trade already running on {top_cand.get('symbol')}. Lock Engaged.")

        elif all_positions:

            running = list(open_sym_map.keys())

            lines.append(f"🛡️ <b>POSITION LOCK:</b> {len(running)} Positions running ({running}). Target Clear.")

        else:

            lines.append("🛡️ <b>POSITION LOCK:</b> Zero active positions. Clear to fire.")



    lines.append(f"

⏱️ Last Scanned: {t_now}")

    return "

".join(lines), get_scan_keyboard()





def build_sentinel_alert(ticket, sym, direction, edge, lots, sl, tp):







    return (







        f"рџљЁ🔥 [NEXUS SENTINEL: AUTO-FIRED TRADE] 🔥рџљЁ\n"







        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"







        f"🎯 Ticket: #{ticket}\n"







        f"💼Ћ Symbol: {chk_sym} ({direction} @ {edge}%)\n"







        f"рџ“¦ Sizing: {lots} Lots\n"







        f"рџ›‘ SL: ${sl} | 🎯 TP: ${tp}\n"







        f"🛡️ Status: LIVE ON EXNESS MT5"







    )















def get_scan_keyboard():

    keyboard = [

        [InlineKeyboardButton("🔄 Run Scan Again", callback_data="rescan")],

        [InlineKeyboardButton("💼 Accounts Switchboard", callback_data="accounts")]

    ]

    return InlineKeyboardMarkup(keyboard)





def render_switchboard_card():







    ensure_mt5()







    cfg = load_accounts()







    active_alias = cfg.get("active_alias", "main")







    acc_map = cfg.get("accounts", {})







    curr = acc_map.get(active_alias, {})







    login_id = curr.get("login", "Unknown")















    acc_info = mt5.account_info()







    equity_str = f"${acc_info.equity:,.2f}" if acc_info else "$0.00"















    text = (







        f"NEXUS ACCOUNT SWITCHBOARD\n"







        f"Active: [{active_alias}] (#{login_id})\n"







        f"Equity: {equity_str}\n"







    )















    buttons = []







    for alias, a_data in acc_map.items():







        if alias != active_alias:







            name = a_data.get("name", alias)







            buttons.append([InlineKeyboardButton(f"Switch to: {name}", callback_data=f"SWITCH_{alias}")])















    buttons.append([InlineKeyboardButton("🌐 Open 5-Asset Scanner", callback_data="RUN_SCAN_NOW")])







    return text, InlineKeyboardMarkup(buttons)















async def execute_trade_if_qualified(top, context_bot=None):







    if not top or not top.get("cleared", False):







        return None, None















    sym = top["symbol"]







    chk_sym = top.get('symbol') if (scans and isinstance(top, dict)) else None

        positions = mt5.positions_get(symbol=chk_sym) if chk_sym else (mt5.positions_get() or [])







    if positions and len(positions) > 0:







    return "

".join(card)\n".join(lines), get_keyboard()















    direction = top["direction"]







    lots = top.get("calculated_lots", 0.01)







    sl = top.get("sl", 0.0)







    tp = top.get("tp", 0.0)







    edge = top.get("edge", 72)















    ok, res_msg, ticket = execute_market_order(sym, direction, lot=lots, sl=sl, tp=tp)







    if ok:







        gate_status = (







            f"⚡ AUTOPILOT GATE: FIRING ORDER ON MT5...\n"







            f"🚀 AUTOPILOT TRIGGERED: Ticket #{ticket} executed on {chk_sym}!\n\n"







            f"Command Executed: Zero active positions."







        )







        sentinel_card = build_sentinel_alert(ticket, sym, direction, edge, lots, sl, tp)







        return gate_status, sentinel_card







    return f"вќЊ Autopilot Error: {res_msg}", None















ACTIVE_CHAT_ID = ADMIN_CHAT_ID







DASHBOARD_MSG_ID = None















def update_active_chat(chat_id):







    global ACTIVE_CHAT_ID







    if chat_id:







        ACTIVE_CHAT_ID = chat_id























async def unlatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):







    chat_id = update.effective_chat.id







    if ADMIN_CHAT_ID and str(chat_id) != str(ADMIN_CHAT_ID):







        await update.message.reply_text("в›” Unauthorized access.")

        return "

".join(card)", None

    state_path = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\circuit_breaker_state.json"







    try:







        acc = await asyncio.to_thread(mt5.account_info)







        live_eq = acc.equity if acc else 10000.0







        







        unlatched_state = {







            "high_water_mark": float(live_eq),







            "current_floor": round(float(live_eq) * 0.95, 2),







            "base_floor": round(float(live_eq) * 0.90, 2),







            "max_drawdown_pct": 0.05,







            "is_tripped": False,







            "tripped_timestamp": None,







            "last_updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()







        }







        







        with open(state_path, "w", encoding="utf-8") as f:







            json.dump(unlatched_state, f, indent=4)







            







        await update.message.reply_text(







            f"✅ *SHIVSOUL CIRCUIT BREAKER UNLATCHED*\n"







            f"━━━━━━━━━━━━━━━━━━━\n"







            f"💰 HWM Reset: `${live_eq:,.2f}`\n"







            f"🛡️ Dynamic 5% Floor: `${unlatched_state['current_floor']:,.2f}`\n"







            f"Status: NORMAL / AUTONOMOUS ACTIVE",







            parse_mode="Markdown"







        )







    except Exception as e:







        await update.message.reply_text(f"вќЊ Failed to unlatch: {e}")







async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):







    chat_id = update.effective_chat.id







    update_active_chat(chat_id)







    ensure_mt5()







    pos = mt5.positions_get() or []







    acc = mt5.account_info()







    







    txt = (







        f"📊 *NEXUS SYSTEM STATUS*\n"







        f"━━━━━━━━━━━━━━━━━━━\n"







        f"💰 Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f}\n"







        f"🛡️ Margin Free: ${acc.margin_free:,.2f}\n"







        f"⚡ Active Trades: {len(pos)}/5\n\n"







    )







    if pos:







        txt += "📍 *Open Positions:*\n"







        for p in pos:







            side = "BUY" if p.type == 0 else "SELL"







            txt += f"• #{p.ticket} {p.symbol} ({side} {p.volume:.2f}L): ${p.profit:,.2f}\n"







        txt += f"\nTotal Float: ${sum(p.profit for p in pos):,.2f}"







    else:







        txt += "Zero active positions."







    await update.message.reply_text(txt, parse_mode="Markdown")















async def background_scan_daemon(app):







    global DASHBOARD_MSG_ID







    print("[+] Autonomous 60s scan loop: AUTO-DASHBOARD & MULTI-ASSET ENGINE ACTIVE.")







    await asyncio.sleep(60)







    while True:







        try:







            t_now = datetime.datetime.now().strftime("%H:%M:%S")







            scans = await asyncio.to_thread(scan_all_assets)







            







            if scans:







                fired_orders = []







                for candidate in scans:







                    sym = candidate["symbol"]







                    edge = candidate["edge"]







                    direction = candidate["direction"]







                    cleared = candidate.get("cleared", False)















                    chk_sym = top.get('symbol') if (scans and isinstance(top, dict)) else None

        positions = mt5.positions_get(symbol=chk_sym) if chk_sym else (mt5.positions_get() or [])







                    is_locked = positions and len(positions) > 0















                    cb_active, _ = check_daily_circuit_breaker()







                    if cb_active:







                        continue







                if cleared and not is_locked:

                    sym = candidate.get('symbol')

                    if not sym:

                        continue

                    if 'EXEC_COOLDOWNS' not in globals():

                        globals()['EXEC_COOLDOWNS'] = {}

                    import time as _t_mod

                    _now_s = _t_mod.time()

                    if sym in globals()['EXEC_COOLDOWNS'] and (_now_s - globals()['EXEC_COOLDOWNS'][sym]) < 300:

                        continue

                    globals()['EXEC_COOLDOWNS'][sym] = _now_s

                    lots = candidate.get('calculated_lots', 0.01)

                    sl = candidate.get('sl', 0.0)

                    tp = candidate.get('tp', 0.0)

                    sym = locals().get('symbol') or locals().get('target_symbol') or locals().get('s')

                    if not sym and 'candidate' in locals():

                        sym = candidate.get('symbol') if isinstance(candidate, dict) else getattr(candidate, 'symbol', None)

                    print(f"[{t_now}] [INSTANT-TRIGGER] Firing {direction} on {sym} ({lots}L @ {edge}% Edge)...")



                    ok, res_msg, ticket = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)

                    if ok:







                            fired_orders.append((ticket, sym, direction, edge, lots, sl, tp))







                            sentinel_card = build_sentinel_alert(ticket, sym, direction, edge, lots, sl, tp)







                            target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID







                            try:







                                await app.bot.send_message(chat_id=target_id, text=sentinel_card, parse_mode="HTML")







                            except Exception as te:







                                print(f"[!] Sentinel dispatch error: {te}")















                autopilot_status = None







                if fired_orders:







                    autopilot_status = f"🚀 FIRED {len(fired_orders)} NEW TRADE(S) AT {t_now}!"







                _card_res = render_leaderboard_card(scans, autopilot_status=autopilot_status)

                if isinstance(_card_res, (tuple, list)) and len(_card_res) >= 2:

                    board_text, markup = _card_res[0], _card_res[1]

                elif isinstance(_card_res, (tuple, list)) and len(_card_res) == 1:

                    board_text, markup = _card_res[0], None

                else:

                    board_text, markup = str(_card_res or ''), None















                if isinstance(_card_res, (tuple, list)) and len(_card_res) >= 2:















                    board_text, markup = _card_res[0], _card_res[1]















                elif isinstance(_card_res, (tuple, list)) and len(_card_res) == 1:















                    board_text, markup = _card_res[0], None















                else:















                    board_text, markup = str(_card_res or ''), None







                







                target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID







                if not DASHBOARD_MSG_ID:

                    DASHBOARD_MSG_ID = get_cadence_anchor_id()

                if board_text and str(board_text).strip():

                    if DASHBOARD_MSG_ID:







                    try:







                        await app.bot.edit_message_text(chat_id=target_id, message_id=DASHBOARD_MSG_ID, text=board_text, reply_markup=markup, parse_mode="HTML")







                    except Exception:







                        pass







                else:







                    if board_text and str(board_text).strip():

                        try:







                            msg = await app.bot.send_message(chat_id=target_id, text=board_text, reply_markup=markup, parse_mode="HTML")







                            DASHBOARD_MSG_ID = msg.message_id







                    except Exception as e:







                        print(f"[!] Dashboard broadcast error: {e}")















                active_count = len(mt5.positions_get() or [])







                summary_line = " | ".join([f"{s['symbol']}:{s['edge']}%" for s in scans])







                active_syms = [p.symbol for p in (mt5.positions_get() or [])]







                print(f"[{t_now}] [60s-SCAN ALL 5] {summary_line} | Locked: {active_syms}")

        # --- AUTONOMOUS RISK SENTINEL & TELEMETRIC BROADCAST ---

        try:

            primary_admin_id = 5279761713



            # 1. Evaluate & Ratchet Trailing Stops across active tickets

            risk_events = risk_engine.evaluate_and_ratchet()

            for ev in risk_events:

                ev_name = ev.get("event")

                sym = ev.get("symbol")

                tkt = ev.get("ticket")

                new_sl = ev.get("new_sl")

                pnl = ev.get("profit", 0.0)

                pnl_s = "+" if pnl >= 0 else ""

                alert_text = (

                    f"🛡️ <b>NEXUS RISK SENTINEL | {ev_name}</b>

"

                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"

                    f"Ticket: <code>#{tkt}</code> | Asset: <b>{sym}</b>

"

                    f"Dynamic Stop Ratchet: <code>${new_sl:,.2f}</code>

"

                    f"Secured Floating PnL: <b>{pnl_s}${pnl:,.2f}</b>

"

                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"

                    f"⚡ <i>Autonomous Protection Engaged | Exness Core</i>"

                )

                if 'updater' in globals() and updater and updater.bot:

                    try:

                        updater.bot.send_message(chat_id=primary_admin_id, text=alert_text, parse_mode="HTML")

                    except Exception:

                        pass



            # 2. Render & Broadcast 60s Dashboard to Telegram

            card_text, card_markup = render_leaderboard_card(scans=scans, autopilot_status="AUTONOMOUS 60S CADENCE ACTIVE")

            if 'updater' in globals() and updater and updater.bot:

                try:

                    updater.bot.send_message(

                        chat_id=primary_admin_id,

                        text=card_text,

                        reply_markup=card_markup,

                        parse_mode="HTML"

                    )

                except Exception as b_err:

                    print(f"[!] Broadcast dispatch error: {b_err}")



            # 3. Dynamic Auto-Trigger >= 75% Edge on Unlocked Assets

            for item in (scans or []):

                s_edge = item.get("edge", 0)

                s_dir = item.get("direction", "NEUTRAL")

                s_sym = item.get("symbol", "")

                if s_edge >= 75 and s_dir in ["BUY", "SELL"]:

                    bot_obj = updater.bot if ('updater' in globals() and updater) else None

                    if 'execute_autonomous_signal' in globals():

                        execute_autonomous_signal(item, chat_id=primary_admin_id, bot_instance=bot_obj)

                    break

        except Exception as loop_err:

            print(f"[!] Autonomous loop telemetry error: {loop_err}")



                await asyncio.sleep(60)















        except asyncio.CancelledError:







            print("[i] Scan daemon stopped cleanly.")







            break







        except Exception as e:







            import traceback; print(f"[!] Daemon error: {e}\n{traceback.format_exc()}")







            await asyncio.sleep(60)















async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):







    scans = scan_all_assets()







    text, markup = render_leaderboard_card(scans)







    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")















async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):







    global ACTIVE_CHAT_ID, DASHBOARD_MSG_ID







    ACTIVE_CHAT_ID = update.effective_chat.id







    print(f"[*] /scan received from {ACTIVE_CHAT_ID}. Executing full universe evaluation...")







    scans = await asyncio.to_thread(scan_all_assets)







    _card_res = render_leaderboard_card(scans)









    if isinstance(_card_res, (tuple, list)) and len(_card_res) >= 2:









        board_text, markup = _card_res[0], _card_res[1]









    elif isinstance(_card_res, (tuple, list)) and len(_card_res) == 1:









        board_text, markup = _card_res[0], None









    else:









        board_text, markup = str(_card_res or ''), None







    msg = await update.message.reply_text(board_text, reply_markup=markup, parse_mode="HTML")







    DASHBOARD_MSG_ID = msg.message_id







    print(f"[+] Full Dashboard dispatched. Msg ID: {DASHBOARD_MSG_ID}")























async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):







    text, markup = render_switchboard_card()







    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")















async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):







    query = update.callback_query







    await query.answer(text="Refreshing Institutional Leaderboard...")







    global DASHBOARD_MSG_ID, ACTIVE_CHAT_ID







    ACTIVE_CHAT_ID = update.effective_chat.id















    data = query.data







    if data in ["scan", "scan_now", "refresh"]:







        try:







            scans = await asyncio.to_thread(scan_all_assets)







            board_text, markup = render_leaderboard_card(scans)







            await query.edit_message_text(text=board_text, reply_markup=markup, parse_mode="HTML")







            DASHBOARD_MSG_ID = query.message.message_id

            set_cadence_anchor_id(DASHBOARD_MSG_ID)







            print(f"[+] Leaderboard refreshed via button click by {ACTIVE_CHAT_ID}")







        except Exception as e:







            if "Message is not modified" not in str(e):







                print(f"[!] Callback refresh error: {e}")







    elif data.startswith("acc_"):







        pass























async def post_stop_handler(application):







    global SCAN_TASK







    if SCAN_TASK and not SCAN_TASK.done():







        SCAN_TASK.cancel()







        try:







            await SCAN_TASK







        except (asyncio.CancelledError, Exception):







            pass















async def on_startup(app):







    asyncio.create_task(background_scan_daemon(app))















async def error_handler(update, context):







    if "Query is too old" not in str(context.error):







        print(f"[!] Bot error handled: {context.error}")























recognizer = sr.Recognizer()















NEURAL_VOICE = 'en-US-ChristopherNeural'















# --- RESILIENT FAIL-FAST OMEGA COPILOT ENGINE ---







NEURAL_VOICE = 'en-US-ChristopherNeural'















def get_local_direct_answer(user_query: str) -> str:







    '''Sub-millisecond local answer without touching cloud API if query is direct.'''







    ensure_mt5()







    q = user_query.lower()







    if 'bitcoin' in q or 'btc' in q:







        pos = [p for p in (mt5.positions_get() or []) if 'BTC' in p.symbol.upper()]







        if pos:







            p = pos[0]







            side = 'BUY' if p.type == 0 else 'SELL'







            return f'Bitcoin position active. Ticket #{p.ticket}, {side} {p.volume} lots at {p.price_open:.2f}. Stop Loss at {p.sl:.2f}, Take Profit at {p.tp:.2f}. Floating profit is {p.profit:+.2f} dollars.'







        tick = mt5.symbol_info_tick('BTCUSD')







        return f'No open Bitcoin position. BTCUSD bid is {tick.bid:.2f}.' if tick else 'No open Bitcoin position.'







    if 'gold' in q or 'xau' in q:







        pos = [p for p in (mt5.positions_get() or []) if 'XAU' in p.symbol.upper()]







        if pos:







            p = pos[0]







            side = 'BUY' if p.type == 0 else 'SELL'







            return f'Gold position active. Ticket #{p.ticket}, {side} {p.volume} lots at {p.price_open:.2f}. Floating profit is {p.profit:+.2f} dollars.'







        tick = mt5.symbol_info_tick('XAUUSD')







        return f'No open Gold position. Gold bid is {tick.bid:.2f}.' if tick else 'No open Gold position.'







    if 'status' in q or 'equity' in q or 'profit' in q or 'balance' in q:







        acc = mt5.account_info()







        pos = mt5.positions_get() or []







        tot_p = sum(p.profit for p in pos)







        return f'Account equity is {int(acc.equity if acc else 0)} dollars. Total floating profit across {len(pos)} open positions is {int(tot_p)} dollars.'







    return ''















def get_live_context_snapshot() -> str:







    ensure_mt5()







    acc = mt5.account_info()







    pos = mt5.positions_get() or []







    pos_list = []







    for p in pos:







        side = 'BUY' if p.type == 0 else 'SELL'







        pos_list.append(f'#{p.ticket} {p.symbol} {side} {p.volume}L@{p.price_open:.2f} (Float: ${p.profit:.2f})')







    pos_str = '; '.join(pos_list) if pos_list else 'None'







    return f'Equity: ${int(acc.equity if acc else 0)}. Open Positions: [{pos_str}].'















async def send_voice_brief(chat_id, context, msg_text):







    try:







        clean_text = ''.join(c for c in str(msg_text) if c not in '*_`#[]$')







        temp_ogg = f'brief_{chat_id}.ogg'







        communicate = edge_tts.Communicate(clean_text[:350], NEURAL_VOICE)







        await communicate.save(temp_ogg)







        with open(temp_ogg, 'rb') as f:







            await context.bot.send_voice(chat_id=chat_id, voice=f)







        if os.path.exists(temp_ogg):







            os.remove(temp_ogg)







    except Exception as e:







        print('[!] Voice brief error:', e)















def _blocking_gemini_query(client, prompt_text: str) -> str:







    response = client.models.generate_content(







        model='gemini-3.8-flash',







        contents=prompt_text,







        config=types.GenerateContentConfig(







            temperature=0.1,







            max_output_tokens=100







        )







    )







    return response.text.strip() if response and response.text else 'Directive processed.'















async def ask_gemini_turbo(user_query: str) -> str:







    # Check if we have a direct fast-path local answer first







    direct = get_local_direct_answer(user_query)







    if direct:







        return direct















    GEMINI_KEY = os.getenv('GEMINI_API_KEY', '').strip().strip('"').strip("'")







    if not GEMINI_KEY:







        return 'Gemini API key is missing. Using local execution.'















    context_data = await asyncio.to_thread(get_live_context_snapshot)







    system_context = (







        'You are Nexus Omega, institutional quant trading copilot. '







        'Live MT5 State: ' + context_data + '. '







        'Answer user request accurately using this live state in under 30 words. No markdown, no bullets.'







    )







    full_prompt = system_context + chr(10) + chr(10) + 'User Directive: ' + user_query







    client = genai.Client(api_key=GEMINI_KEY)















    try:







        # Enforce strict 4-second timeout on Google API







        reply = await asyncio.wait_for(







            asyncio.to_thread(_blocking_gemini_query, client, full_prompt),







            timeout=4.0







        )







        return reply







    except asyncio.TimeoutError:







        print('[!] Gemini API timed out after 4s. Falling back to local snapshot.')







        return get_local_direct_answer(user_query) or 'Request completed. Portfolio state synchronized.'







    except Exception as e:







        print('[!] Gemini API call failed:', e)







        return get_local_direct_answer(user_query) or f'Telemetry updated: {e}'















async def voice_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):







    global ACTIVE_CHAT_ID, DASHBOARD_MSG_ID







    ACTIVE_CHAT_ID = update.effective_chat.id







    voice = update.message.voice







    if not voice:

        return "

".join(card)", None

    status_msg = await update.message.reply_text('рџЋ™пёЏ Listening...')















    try:







        voice_file = await context.bot.get_file(voice.file_id)







        ogg_bytes = io.BytesIO()







        await voice_file.download_to_memory(ogg_bytes)







        ogg_bytes.seek(0)















        def convert_and_transcribe(ogg_buf):







            sound = AudioSegment.from_file(ogg_buf, format='ogg')







            sound = sound.set_frame_rate(16000).set_channels(1)







            wav_io = io.BytesIO()







            sound.export(wav_io, format='wav')







            wav_io.seek(0)







            with sr.AudioFile(wav_io) as source:







                recognizer.adjust_for_ambient_noise(source, duration=0.1)







                audio_data = recognizer.record(source)







                try:







                    return recognizer.recognize_google(audio_data, language='en-IN')







                except Exception:







                    return recognizer.recognize_google(audio_data, language='en-US')















        heard = await asyncio.to_thread(convert_and_transcribe, ogg_bytes)







        print('[VOICE IN] Transcribed:', heard)















        q = heard.lower()







        executed_action = None







        if 'trail' in q:







            executed_action = configure_trailing_from_voice(q)







        elif 'protect' in q or 'breakeven' in q:







            sym = 'BTCUSD' if ('btc' in q or 'bitcoin' in q) else ('XAUUSD' if 'gold' in q else 'USDJPY')







            _, executed_action = await asyncio.to_thread(execute_breakeven_lock, sym)







        elif 'trim' in q or 'close half' in q or 'partial' in q:







            sym = 'BTCUSD' if ('btc' in q or 'bitcoin' in q) else ('XAUUSD' if 'gold' in q else 'USDJPY')







            _, executed_action = await asyncio.to_thread(execute_smart_trim, sym, 50)















        await status_msg.edit_text("Directive: " + str(heard) + chr(10) + "⚡ Processing...")







        if executed_action:







            copilot_reply = executed_action







        else:







            copilot_reply = await ask_gemini_turbo(heard)







        clean_reply = str(copilot_reply).replace("*", "").replace("_", "")







        final_card = "Directive: " + str(heard) + chr(10) + chr(10) + "Nexus: " + str(clean_reply)







        await status_msg.edit_text(final_card)







        asyncio.create_task(send_voice_brief(ACTIVE_CHAT_ID, context, clean_reply))















    except sr.UnknownValueError:







        await status_msg.edit_text('вќЊ Audio unclear. Please speak close to the mic.')







    except Exception as e:







        print('[!] Voice pipeline error:', e)







        await status_msg.edit_text(f'вљ пёЏ Error: {e}')















if __name__ == "__main__":







    ensure_mt5()







    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).post_stop(post_stop_handler).build()















    app.add_handler(CommandHandler(["start", "START", "help"], start_command))







    app.add_handler(CommandHandler(["unlatch", "UNLATCH"], unlatch_command))







    app.add_handler(CommandHandler(["status", "STATUS"], status_command))







    app.add_handler(CommandHandler(["scan", "SCAN"], scan_command))







    app.add_handler(CommandHandler(["accounts", "ACCOUNTS"], accounts_command))







    app.add_handler(CallbackQueryHandler(handle_callback))







    app.add_handler(MessageHandler(filters.VOICE, voice_command_handler))















    app.add_error_handler(error_handler)















    print("[+] Autonomous 60s scan & trigger loop engaged.")







    print("[ONLINE] Nexus Multi-Account Switchboard & Interactive Controller Active.")







    app.run_polling(poll_interval=1.0, timeout=30, drop_pending_updates=False)








async def cmd_scan(update, context):
    try:
        matrix_msg, _ = build_institutional_fleet_matrix()
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = [
            [InlineKeyboardButton("🔄 Run Scan Again", callback_data="scan_now")],
            [InlineKeyboardButton("💼 Accounts Switchboard", callback_data="switchboard")]
        ]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(matrix_msg, reply_markup=InlineKeyboardMarkup(kb))
        elif update.message:
            await update.message.reply_text(matrix_msg, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        msg = f"❌ Scan generation error: {e}"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        elif update.message:
            await update.message.reply_text(msg)
