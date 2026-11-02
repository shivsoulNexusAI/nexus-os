import os
import json
import math
import numpy as np
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

RECAP_HISTORY_FILE = "recap_dispatch_history.json"

def get_recap_history():
    if os.path.exists(RECAP_HISTORY_FILE):
        try:
            with open(RECAP_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def mark_recap_sent(key: str):
    data = get_recap_history()
    data[key] = datetime.now(timezone.utc).isoformat()
    try:
        with open(RECAP_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[!] Failed to write recap history: {e}")

def calculate_advanced_metrics(closed_trades, starting_balance):
    if not closed_trades:
        return {
            "sharpe": 0.0,
            "max_dd_usd": 0.0,
            "max_dd_pct": 0.0,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0
        }

    pnls = [t["net_pnl"] for t in closed_trades]
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]

    win_rate = (len(wins) / len(pnls)) * 100.0 if pnls else 0.0
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)
    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0

    if len(pnls) >= 2:
        mean_pnl = float(np.mean(pnls))
        std_pnl = float(np.std(pnls, ddof=1))
        sharpe = (mean_pnl / std_pnl) * math.sqrt(min(252, len(pnls) * 52)) if std_pnl > 1e-6 else 0.0
    else:
        sharpe = 0.0

    equity_curve = [starting_balance]
    curr = starting_balance
    for p in pnls:
        curr += p
        equity_curve.append(curr)

    peak = equity_curve[0]
    max_dd_usd = 0.0
    max_dd_pct = 0.0

    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = (dd / peak) * 100.0 if peak > 0 else 0.0
        if dd > max_dd_usd:
            max_dd_usd = dd
            max_dd_pct = dd_pct

    return {
        "sharpe": sharpe,
        "max_dd_usd": max_dd_usd,
        "max_dd_pct": max_dd_pct,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss
    }

def generate_recap_payload(period="DAILY") -> str:
    now = datetime.now(timezone.utc)
    if period == "DAILY":
        from_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        title = "DAILY PERFORMANCE & AUDIT"
    elif period == "WEEKLY":
        from_date = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        title = "WEEKLY MASTER PERFORMANCE"
    else:
        from_date = now - timedelta(hours=24)
        title = "24-HOUR PERFORMANCE AUDIT"

    if not mt5 or not mt5.initialize():
        return "🚨 MT5 connection unavailable to generate recap report."

    acc = mt5.account_info()
    if not acc:
        return "🚨 Failed to retrieve MT5 account state for recap."

    deals = mt5.history_deals_get(from_date, now)
    closed_trades = []
    gross_trading_pnl = 0.0
    total_swap = 0.0
    total_commission = 0.0
    net_realized_pnl = 0.0
    best_trade = None
    worst_trade = None

    if deals:
        for d in deals:
            if d.entry == mt5.DEAL_ENTRY_OUT and (d.profit != 0 or d.swap != 0 or d.commission != 0):
                net = d.profit + d.swap + d.commission
                gross_trading_pnl += d.profit
                total_swap += d.swap
                total_commission += d.commission
                net_realized_pnl += net
                closed_trades.append({"ticket": d.position_id, "net_pnl": net})
                if net > 0:
                    if best_trade is None or net > best_trade["pnl"]:
                        best_trade = {"symbol": d.symbol, "pnl": net}
                elif net < 0:
                    if worst_trade is None or net < worst_trade["pnl"]:
                        worst_trade = {"symbol": d.symbol, "pnl": net}

    period_starting_balance = acc.balance - net_realized_pnl
    stats = calculate_advanced_metrics(closed_trades, period_starting_balance)

    positions = mt5.positions_get()
    open_count = len(positions) if positions else 0
    floating_pnl = sum(p.profit for p in positions) if positions else 0.0
    live_floating_dd_usd = max(0.0, acc.balance - acc.equity)
    live_floating_dd_pct = (live_floating_dd_usd / acc.balance * 100.0) if acc.balance > 0 else 0.0

    runners_active = 0
    if os.path.exists("partial_tp_registry.json"):
        try:
            with open("partial_tp_registry.json", "r", encoding="utf-8") as f:
                registry = set(json.load(f))
            if positions:
                runners_active = sum(1 for p in positions if p.ticket in registry)
        except Exception:
            runners_active = 0

    net_sign = "+" if net_realized_pnl >= 0 else ""
    gross_sign = "+" if gross_trading_pnl >= 0 else ""
    swap_sign = "+" if total_swap >= 0 else ""
    comm_sign = "-" if total_commission < 0 else ""
    float_sign = "+" if floating_pnl >= 0 else ""

    best_str = f"{best_trade['symbol']} (+${best_trade['pnl']:,.2f})" if best_trade else "None"
    worst_str = f"{worst_trade['symbol']} (-${abs(worst_trade['pnl']):,.2f})" if worst_trade else "None"

    return (
        f"📊 <b>QUANT NEXUS // {title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ <b>Generated:</b> <code>{now.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>\n"
        f"🏦 <b>Terminal:</b> <code>#{acc.login}</code> ({acc.server})\n\n"
        f"💰 <b>CAPITAL & RISK POSTURE</b>\n"
        f"• <b>Account Balance:</b> <code>${acc.balance:,.2f}</code>\n"
        f"• <b>Live Equity:</b> <code>${acc.equity:,.2f}</code>\n"
        f"• <b>Free Margin:</b> <code>${acc.margin_free:,.2f}</code>\n"
        f"• <b>Net Realized PnL:</b> <code>{net_sign}${net_realized_pnl:,.2f}</code>\n"
        f"• <b>Floating Exposure:</b> <code>{float_sign}${floating_pnl:,.2f}</code>\n\n"
        f"📉 <b>DRAWDOWN & RISK METRICS</b>\n"
        f"• <b>Sharpe Ratio:</b> <code>{stats['sharpe']:.2f}</code> (Annualized Est.)\n"
        f"• <b>Max Closed DD:</b> <code>${stats['max_dd_usd']:,.2f}</code> ({stats['max_dd_pct']:.2f}%)\n"
        f"• <b>Live Floating DD:</b> <code>${live_floating_dd_usd:,.2f}</code> ({live_floating_dd_pct:.2f}%)\n"
        f"• <b>Profit Factor:</b> <code>{stats['profit_factor']:.2f}</code>\n"
        f"• <b>Win Rate:</b> <code>{stats['win_rate']:.1f}%</code> ({len(closed_trades)} deals)\n\n"
        f"💳 <b>FEE & FRICTION AUDIT</b>\n"
        f"• <b>Gross Trading PnL:</b> <code>{gross_sign}${gross_trading_pnl:,.2f}</code>\n"
        f"• <b>Financing Swap:</b> <code>{swap_sign}${total_swap:,.2f}</code>\n"
        f"• <b>Broker Commissions:</b> <code>{comm_sign}${abs(total_commission):,.2f}</code>\n"
        f"• <b>Net Friction Impact:</b> <code>${(total_swap + total_commission):,.2f}</code>\n\n"
        f"🎯 <b>EXECUTION HIGHLIGHTS</b>\n"
        f"• <b>Best Deal:</b> <code>{best_str}</code>\n"
        f"• <b>Worst Deal:</b> <code>{worst_str}</code>\n"
        f"• <b>Avg Win / Loss:</b> <code>+${stats['avg_win']:,.2f} / -${stats['avg_loss']:,.2f}</code>\n"
        f"• <b>Portfolio Allocation:</b> <code>{open_count}/6 Slots</code> ({max(0, 6 - open_count)} Open)\n"
        f"• <b>Armored Free-Runners:</b> <code>{runners_active} Active</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <i>Institutional Telemetry // Sovereign Nexus V6</i>"
    )

def generate_open_positions_payload() -> str:
    if not mt5 or not mt5.initialize():
        return "🚨 MT5 connection unavailable."
    acc = mt5.account_info()
    positions = mt5.positions_get()
    now = datetime.now(timezone.utc)

    if not positions:
        return (
            f"🛡️ <b>QUANT NEXUS // ACTIVE PORTFOLIO AUDIT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ <code>{now.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>\n\n"
            f"<i>No open positions active. Auto-fire hunting for confluence setups (4/6 slots free).</i>"
        )

    reg = set()
    if os.path.exists("partial_tp_registry.json"):
        try:
            with open("partial_tp_registry.json", "r", encoding="utf-8") as f:
                reg = set(json.load(f))
        except Exception:
            pass

    lines = [
        "🛡️ <b>QUANT NEXUS // ACTIVE PORTFOLIO POSITIONS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏱️ <code>{now.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>",
        f"🏦 <b>Terminal:</b> <code>#{acc.login}</code> | Equity: <code>${acc.equity:,.2f}</code>\n"
    ]

    total_floating = 0.0
    for p in positions:
        total_floating += p.profit
        side = "🟢 BUY" if p.type == mt5.ORDER_TYPE_BUY else "🔴 SELL"
        is_runner = " [🛡️ FREE-RUNNER]" if p.ticket in reg else ""
        lines.append(
            f"• <b>{p.symbol}</b>: {side} <code>{p.volume:.2f}L</code>{is_runner}\n"
            f"  └ Ticket: <code>#{p.ticket}</code> | PnL: <code>{'+' if p.profit >= 0 else ''}${p.profit:,.2f}</code> | SL: <code>{p.sl:.5f}</code>"
        )

    lines.append(f"\n💰 <b>Net Floating PnL:</b> <code>{'+' if total_floating >= 0 else ''}${total_floating:,.2f}</code>")
    lines.append(f"🛡️ <b>Capacity:</b> <code>{len(positions)}/6 Slots</code> ({max(0, 6 - len(positions))} Open)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔒 <i>Tap buttons below to toggle performance audit views.</i>")
    return "\n".join(lines)

def execute_manual_break_even(ticket: int) -> tuple[bool, str]:
    if not mt5 or not mt5.initialize():
        return False, "MT5 terminal unavailable"
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False, f"Ticket #{ticket} not found or already closed"
    pos = positions[0]
    sym_info = mt5.symbol_info(pos.symbol)
    if not sym_info:
        return False, f"Failed to query symbol info for {pos.symbol}"

    entry = pos.price_open
    offset = 20 * sym_info.point
    new_sl = (entry + offset) if pos.type == mt5.ORDER_TYPE_BUY else (entry - offset)
    new_sl = round(new_sl, sym_info.digits)

    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": pos.symbol,
        "sl": new_sl,
        "tp": pos.tp
    }
    res = mt5.order_send(req)
    if not res or res.retcode != mt5.TRADE_RETCODE_DONE:
        err = res.comment if res else "Unknown order error"
        return False, f"MT5 reject: {err}"

    if os.path.exists("partial_tp_registry.json"):
        try:
            with open("partial_tp_registry.json", "r", encoding="utf-8") as f:
                reg = set(json.load(f))
            reg.add(ticket)
            with open("partial_tp_registry.json", "w", encoding="utf-8") as f:
                json.dump(list(reg), f)
        except Exception:
            pass

    return True, f"🛡️ #{ticket} {pos.symbol} SL locked at {new_sl:.5f} (BE + 2 pips)"

def get_telegram_recap_markup():
    keyboard = [
        [
            InlineKeyboardButton("📅 Daily Audit", callback_data="recap_daily"),
            InlineKeyboardButton("📊 Weekly Audit", callback_data="recap_weekly")
        ],
        [
            InlineKeyboardButton("🛡️ Active Positions", callback_data="recap_positions"),
            InlineKeyboardButton("🔄 Live Refresh", callback_data="recap_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_telegram_positions_markup():
    keyboard = []
    if mt5 and mt5.initialize():
        positions = mt5.positions_get()
        reg = set()
        if os.path.exists("partial_tp_registry.json"):
            try:
                with open("partial_tp_registry.json", "r", encoding="utf-8") as f:
                    reg = set(json.load(f))
            except Exception:
                pass
        if positions:
            for p in positions:
                side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                if p.ticket in reg:
                    keyboard.append([InlineKeyboardButton(f"✅ Armored #{p.ticket} ({p.symbol})", callback_data=f"lock_be_noop_{p.ticket}")])
                else:
                    keyboard.append([
                InlineKeyboardButton(f"🛡️ Lock BE #{p.ticket}", callback_data=f"lock_be_{p.ticket}"),
                InlineKeyboardButton(f"💰 Bank 50% #{p.ticket}", callback_data=f"bank_50_{p.ticket}")
            ])

    keyboard.append([
        InlineKeyboardButton("📅 Daily Audit", callback_data="recap_daily"),
        InlineKeyboardButton("📊 Weekly Audit", callback_data="recap_weekly")
    ])
    keyboard.append([InlineKeyboardButton("🔄 Refresh Positions", callback_data="recap_positions")])
    return InlineKeyboardMarkup(keyboard)

async def handle_recap_command(update, context):
    try:
        report = generate_recap_payload("DAILY")
        await update.message.reply_text(report, parse_mode="HTML", reply_markup=get_telegram_recap_markup())
    except Exception as e:
        await update.message.reply_text(f"🚨 Failed to generate recap: {e}")

async def handle_recap_callback(update, context):
    query = update.callback_query
    data = query.data

    if data.startswith("lock_be_noop_"):
        await query.answer("This position is already secured at Break-Even.", show_alert=False)
        return

    
    
    elif data == "emergency_kill_all":
        try:
            success, msg = execute_emergency_close_all()
            await query.answer(f"{'🚨' if success else '⚠️'} {msg}", show_alert=True)
            text, markup = generate_open_positions_payload()
            await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            await query.answer(f"⚠️ Kill switch error: {e}", show_alert=True)

    elif data.startswith("bank_50_"):
        try:
            ticket = int(data.split("_")[2])
            success, msg = execute_partial_close(ticket, pct=0.5)
            await query.answer(f"{'✅' if success else '⚠️'} {msg}", show_alert=True)
            # Re-render active positions with updated volume
            text, markup = generate_open_positions_payload()
            await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            await query.answer(f"⚠️ Error: {e}", show_alert=True)

    if data.startswith("lock_be_"):
        ticket_str = data.replace("lock_be_", "")
        try:
            ticket = int(ticket_str)
            success, msg = execute_manual_break_even(ticket)
            await query.answer(msg, show_alert=True)
            txt = generate_open_positions_payload()
            await query.edit_message_text(text=txt, parse_mode="HTML", reply_markup=get_telegram_positions_markup())
            return
        except Exception as e:
            await query.answer(f"Error locking BE: {e}", show_alert=True)
            return

    await query.answer()
    if data in ["recap_daily", "recap_refresh"]:
        txt = generate_recap_payload("DAILY")
        reply_markup = get_telegram_recap_markup()
    elif data == "recap_weekly":
        txt = generate_recap_payload("WEEKLY")
        reply_markup = get_telegram_recap_markup()
    elif data == "recap_positions":
        txt = generate_open_positions_payload()
        reply_markup = get_telegram_positions_markup()
    else:
        return

    try:
        await query.edit_message_text(text=txt, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        pass

def send_telegram_recap(period="DAILY") -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8883861115:AAFfjNsWgIVzJe2KW0FEvxcUwVFWcVk18I0").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "5279761713").strip()
    if not token or not chat_id:
        return False

    message = generate_recap_payload(period=period)
    raw_markup = {
        "inline_keyboard": [
            [
                {"text": "📅 Daily Audit", "callback_data": "recap_daily"},
                {"text": "📊 Weekly Audit", "callback_data": "recap_weekly"}
            ],
            [
                {"text": "🛡️ Active Positions", "callback_data": "recap_positions"},
                {"text": "🔄 Live Refresh", "callback_data": "recap_refresh"}
            ]
        ]
    }
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML", "reply_markup": raw_markup},
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[!] Failed to dispatch recap: {e}")
        return False


async def autonomous_recap_scheduler():
    """
    Autonomous background scheduler for daily and weekly institutional recaps.
    Dispatches:
      - Daily EOD Recap at 22:00 UTC (after NY market close)
      - Weekly Recap on Friday at 22:05 UTC
    """
    import asyncio
    from datetime import datetime, timezone
    print("[*] Autonomous Recap Scheduler background task initiated.")
    while True:
        try:
            now = datetime.now(timezone.utc)
            date_key = now.strftime("%Y-%m-%d")
            history = get_recap_history()

            # Daily EOD check at 22:00 UTC
            if now.hour == 22 and now.minute == 0:
                daily_key = f"daily_{date_key}"
                if daily_key not in history:
                    send_telegram_recap("DAILY")
                    mark_recap_sent(daily_key)

            # Weekly EOD check on Friday at 22:05 UTC
            if now.weekday() == 4 and now.hour == 22 and now.minute == 5:
                weekly_key = f"weekly_{date_key}"
                if weekly_key not in history:
                    send_telegram_recap("WEEKLY")
                    mark_recap_sent(weekly_key)

            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[!] Autonomous recap scheduler error: {e}")
            await asyncio.sleep(60)



def execute_partial_close(ticket: int, pct: float = 0.5):
    """Partially close open MT5 ticket by pct (default 50%)."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return False, "MT5 failed to initialize"

    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return False, f"Ticket #{ticket} not found or already closed"

    pos = pos[0]
    symbol = pos.symbol
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return False, f"Symbol info for {symbol} not found"

    vol_step = sym_info.volume_step if sym_info.volume_step else 0.01
    min_vol = sym_info.volume_min if sym_info.volume_min else 0.01

    close_vol = round(pos.volume * pct / vol_step) * vol_step
    close_vol = round(close_vol, 2)

    if close_vol < min_vol:
        return False, f"Volume {close_vol} is below minimum lot size ({min_vol})"

    if close_vol >= pos.volume:
        close_vol = pos.volume

    opposite_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False, f"Failed to get live tick for {symbol}"

    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": close_vol,
        "type": opposite_type,
        "position": ticket,
        "price": price,
        "deviation": 25,
        "magic": 777902,
        "comment": f"Bank50 #{ticket}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return True, f"Banked 50% ({close_vol}L) on #{ticket} {symbol} @ {result.price:.5f}"
    else:
        err = result.comment if result else "Order send failed"
        return False, f"MT5 Reject: {err}"



def execute_emergency_close_all():
    """Emergency master liquidation: closes all open MT5 positions immediately."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return False, "MT5 failed to initialize"

    positions = mt5.positions_get()
    if not positions:
        return True, "No open positions to liquidate"

    closed_count = 0
    errors = []

    for p in positions:
        opposite_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        sym_info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not sym_info or not tick:
            errors.append(f"#{p.ticket} tick missing")
            continue

        price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": opposite_type,
            "position": p.ticket,
            "price": price,
            "deviation": 30,
            "magic": 999999,
            "comment": "EMERGENCY_KILL",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed_count += 1
        else:
            errors.append(f"#{p.ticket} reject: {res.comment if res else 'Unknown'}")

    summary = f"Liquidated {closed_count}/{len(positions)} open positions."
    if errors:
        summary += f" Errors: {', '.join(errors[:2])}"
    return closed_count > 0 or len(positions) == 0, summary
