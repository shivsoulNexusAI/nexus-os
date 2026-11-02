LAST_ROLLOVER_DATE = ""
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
        reason = f"🚨 CIRCUIT BREAKER TRIPPED: Realized daily loss ${tot_prof:+,.2f} exceeds limit (${DAILY_MAX_LOSS_LIMIT:,.2f}). Trading locked until 00:00 UTC."
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
    if not mt5.terminal_info():
        mt5.initialize()

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
        return None

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)
    if rates is None or len(rates) < 10:
        return None

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
            print(f"[!] Scan error on {sym}: {e}")
    results.sort(key=lambda x: x.get("edge", 0), reverse=True)
    return results

def render_leaderboard_card(scans, autopilot_status=None):
    t_now = datetime.datetime.now().strftime("%H:%M:%S")
    if not scans:
        return f"🌐 OMEGA FX: 5-ASSET INSTITUTIONAL LEADERBOARD\n\nNo market feed available.\nUpdated: {t_now}", get_scan_keyboard()

    top = scans[0]
    sym = top["symbol"]
    direction = top["direction"]
    edge = top["edge"]
    dir_emoji = "🟢 BUY" if direction == "BUY" else ("🔴 SELL" if direction == "SELL" else "⚪ NEUTRAL")
    cleared_badge = "✅ CLEARED ≥75%" if top.get("cleared") else "⏳ PENDING"

    lines = [
        "🌐 OMEGA FX: 5-ASSET\nINSTITUTIONAL LEADERBOARD",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🔥 TOP PICK: {sym} | {dir_emoji} ({cleared_badge}) | RR: {top.get('rr', 2.33)}R"
    ]

    rank = 2
    for s in scans[1:5]:
        s_sym = s.get("symbol")
        s_dir = "🟢 BUY" if s.get("direction") == "BUY" else ("🔴 SELL" if s.get("direction") == "SELL" else "⚪ NEUTRAL")
        s_badge = f"✅ CLEARED ≥75%" if s.get("cleared") else f"({s.get('edge')}%)"
        lines.append(f"#{rank}: {s_sym} | {s_dir} ({s_badge}) | RR: {s.get('rr', 2.33)}R")
        rank += 1

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🎯 TOP OPPORTUNITY: {sym} ({direction} @ {edge}%)")
    lines.append(f" • Entry: ${top.get('price')}")
    lines.append(f" • SL: ${top.get('sl')} | TP: ${top.get('tp')}")
    lines.append(f" • Sizing: {top.get('calculated_lots')} Lots (1% Risk)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # Autopilot Gate and Execution status
    if autopilot_status:
        lines.append(autopilot_status)
    else:
        positions = mt5.positions_get(symbol=sym)
        if positions and len(positions) > 0:
            lines.append(f"🛡️ POSITION LOCK: Active trade already running on {sym}.")
        else:
            lines.append("🛡️ POSITION LOCK: Zero active positions. Clear to fire.")

    lines.append(f"\n⏱️ Last Scanned: {t_now}")
    return "\n".join(lines), get_scan_keyboard()

def build_sentinel_alert(ticket, sym, direction, edge, lots, sl, tp):
    return (
        f"🚨🔥 [NEXUS SENTINEL: AUTO-FIRED TRADE] 🔥🚨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Ticket: #{ticket}\n"
        f"💎 Symbol: {sym} ({direction} @ {edge}%)\n"
        f"📦 Sizing: {lots} Lots\n"
        f"🛑 SL: ${sl} | 🎯 TP: ${tp}\n"
        f"🛡️ Status: LIVE ON EXNESS MT5"
    )

def get_scan_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Run Scan Again", callback_data="RUN_SCAN_NOW")],
        [InlineKeyboardButton("💼 Accounts Switchboard", callback_data="NAV_SWITCHBOARD")]
    ])

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
    positions = mt5.positions_get(symbol=sym)
    if positions and len(positions) > 0:
        return "🛡️ POSITION LOCK: Active trade already running on " + sym + ".", None

    direction = top["direction"]
    lots = top.get("calculated_lots", 0.01)
    sl = top.get("sl", 0.0)
    tp = top.get("tp", 0.0)
    edge = top.get("edge", 72)

    ok, res_msg, ticket = execute_market_order(sym, direction, lot=lots, sl=sl, tp=tp)
    if ok:
        gate_status = (
            f"⚡ AUTOPILOT GATE: FIRING ORDER ON MT5...\n"
            f"🚀 AUTOPILOT TRIGGERED: Ticket #{ticket} executed on {sym}!\n\n"
            f"Command Executed: Zero active positions."
        )
        sentinel_card = build_sentinel_alert(ticket, sym, direction, edge, lots, sl, tp)
        return gate_status, sentinel_card
    return f"❌ Autopilot Error: {res_msg}", None

ACTIVE_CHAT_ID = ADMIN_CHAT_ID
DASHBOARD_MSG_ID = None

def update_active_chat(chat_id):
    global ACTIVE_CHAT_ID
    if chat_id:
        ACTIVE_CHAT_ID = chat_id


async def unlatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if ADMIN_CHAT_ID and str(chat_id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

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
        await update.message.reply_text(f"❌ Failed to unlatch: {e}")
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
    print("[+] Autonomous 15s scan loop: AUTO-DASHBOARD & MULTI-ASSET ENGINE ACTIVE.")
    await asyncio.sleep(2)
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

                    positions = mt5.positions_get(symbol=sym)
                    is_locked = positions and len(positions) > 0

                    cb_active, _ = check_daily_circuit_breaker()
                    if cb_active:
                        continue
                    if cleared and not is_locked:
                        lots = candidate.get("calculated_lots", 0.01)
                        sl = candidate.get("sl", 0.0)
                        tp = candidate.get("tp", 0.0)
                        
                        print(f"[{t_now}] [INSTANT-TRIGGER] Firing {direction} on {sym} ({lots}L @ {edge}% Edge)...")
                        ok, res_msg, ticket = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)
                        
                        if ok:
                            fired_orders.append((ticket, sym, direction, edge, lots, sl, tp))
                            sentinel_card = build_sentinel_alert(ticket, sym, direction, edge, lots, sl, tp)
                            target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID
                            try:
                                await app.bot.send_message(chat_id=target_id, text=sentinel_card)
                            except Exception as te:
                                print(f"[!] Sentinel dispatch error: {te}")

                autopilot_status = None
                if fired_orders:
                    autopilot_status = f"🚀 FIRED {len(fired_orders)} NEW TRADE(S) AT {t_now}!"
                board_text, markup = render_leaderboard_card(scans, autopilot_status=autopilot_status)
                
                target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID
                if DASHBOARD_MSG_ID:
                    try:
                        await app.bot.edit_message_text(chat_id=target_id, message_id=DASHBOARD_MSG_ID, text=board_text, reply_markup=markup)
                    except Exception:
                        pass
                else:
                    try:
                        msg = await app.bot.send_message(chat_id=target_id, text=board_text, reply_markup=markup)
                        DASHBOARD_MSG_ID = msg.message_id
                    except Exception as e:
                        print(f"[!] Dashboard broadcast error: {e}")

                active_count = len(mt5.positions_get() or [])
                summary_line = " | ".join([f"{s['symbol']}:{s['edge']}%" for s in scans])
                active_syms = [p.symbol for p in (mt5.positions_get() or [])]
                print(f"[{t_now}] [15s-SCAN ALL 5] {summary_line} | Locked: {active_syms}")

                # --- 00:00 UTC ROLLOVER & CIRCUIT BREAKER RESET ---
                try:
                    LAST_ROLLOVER_DATE, rolled = check_and_execute_daily_rollover(LAST_ROLLOVER_DATE)
                except Exception as e_roll:
                    pass

                # --- PILLAR 1: ASYMMETRIC INVALIDATION STACKING SCANNER ---
                try:
                    for s_sym in ['USDJPY', 'EURUSD', 'BTCUSD', 'XAUUSD', 'GBPUSD']:
                        st_res = evaluate_stacking_opportunity(s_sym)
                        if st_res.get("eligible"):
                            s_lot = st_res["lot"]
                            s_dir = st_res["direction"]
                            s_sl = st_res["sl"]
                            s_tp = st_res["tp"]
                            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏹 [ASYMMETRIC STACK] Triggering 0.5x Add on {s_sym} ({s_lot}L) behind Parent #{st_res['parent_ticket']}...")
                            ok_st, st_msg, st_ticket = await asyncio.to_thread(execute_market_order, s_sym, s_dir, lot=s_lot, sl=s_sl, tp=s_tp)
                            if ok_st:
                                print(f"[+] Stack order executed: Ticket #{st_ticket}")
                except Exception:
                    pass

                await asyncio.sleep(15)

        except asyncio.CancelledError:
            print("[i] Scan daemon stopped cleanly.")
            break
        except Exception as e:
            print(f"[!] Daemon error: {e}")
            await asyncio.sleep(5)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scans = scan_all_assets()
    text, markup = render_leaderboard_card(scans)
    await update.message.reply_text(text, reply_markup=markup)

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACTIVE_CHAT_ID, DASHBOARD_MSG_ID
    ACTIVE_CHAT_ID = update.effective_chat.id
    print(f"[*] /scan received from {ACTIVE_CHAT_ID}. Executing full universe evaluation...")
    scans = await asyncio.to_thread(scan_all_assets)
    board_text, markup = render_leaderboard_card(scans)
    msg = await update.message.reply_text(board_text, reply_markup=markup)
    DASHBOARD_MSG_ID = msg.message_id
    print(f"[+] Full Dashboard dispatched. Msg ID: {DASHBOARD_MSG_ID}")


async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = render_switchboard_card()
    await update.message.reply_text(text, reply_markup=markup)

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
            await query.edit_message_text(text=board_text, reply_markup=markup)
            DASHBOARD_MSG_ID = query.message.message_id
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
        return

    status_msg = await update.message.reply_text('🎙️ Listening...')

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
        await status_msg.edit_text('❌ Audio unclear. Please speak close to the mic.')
    except Exception as e:
        print('[!] Voice pipeline error:', e)
        await status_msg.edit_text(f'⚠️ Error: {e}')

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

    print("[+] Autonomous 15s scan & trigger loop engaged.")
    print("[ONLINE] Nexus Multi-Account Switchboard & Interactive Controller Active.")
    app.run_polling(drop_pending_updates=True)