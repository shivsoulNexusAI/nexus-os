import os
import logging
from dotenv import load_dotenv
import MetaTrader5 as mt5
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("QuantNexusBot")

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN missing in .env")

def get_positions_cards():
    if not mt5.initialize():
        return "MT5 Bridge: DISCONNECTED", []
    positions = mt5.positions_get()
    account = mt5.account_info()
    acc_id = account.login if account else "N/A"
    eq = account.equity if account else 0.0
    bal = account.balance if account else 0.0
    status_header = (
        "QUANT NEXUS SYSTEM STATUS: OPERATIONAL\n"
        "------------------------------------\n"
        f"Master Account: #{acc_id}\n"
        f"Equity: ${eq:,.2f} | Balance: ${bal:,.2f}\n"
        "MT5 Bridge: CONNECTED\n"
        "Algorithmic Daemon: ACTIVE\n"
        "Regime Engine: ARMED\n"
        "Reaction Feedback Moat: LISTENING\n"
        "------------------------------------"
    )
    cards = []
    if not positions:
        return status_header, []
    for pos in positions:
        tick = mt5.symbol_info_tick(pos.symbol)
        sym = mt5.symbol_info(pos.symbol)
        curr_price = (tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask) if tick else pos.price_open
        point = sym.point if sym and sym.point else 0.00001
        drift = ((curr_price - pos.price_open) / point) if pos.type == mt5.ORDER_TYPE_BUY else ((pos.price_open - curr_price) / point)
        order_str = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        card_text = (
            f"DRIFT / DELTA ANALYSIS: #{pos.ticket}\n"
            "------------------------------------\n"
            f"Pair: {pos.symbol} ({order_str} {pos.volume}L)\n"
            f"Entry: {pos.price_open:.5f} -> Now: {curr_price:.5f}\n"
            f"Price Drift: {drift:+.1f} pts\n"
            f"Floating Delta: ${pos.profit:+.2f}\n"
            f"SL: {pos.sl:.5f} | TP: {pos.tp:.5f}\n"
            "------------------------------------"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Move to BE", callback_data=f"be:{pos.ticket}"),
                InlineKeyboardButton("Close 50%", callback_data=f"half:{pos.ticket}")
            ],
            [
                InlineKeyboardButton("Close Trade", callback_data=f"close:{pos.ticket}"),
                InlineKeyboardButton("Refresh", callback_data=f"refresh:{pos.ticket}")
            ]
        ])
        cards.append((card_text, keyboard))
    return status_header, cards

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    header, cards = get_positions_cards()
    await update.message.reply_text(header)
    if not cards:
        await update.message.reply_text("No open positions found.")
        return
    for text, markup in cards:
        await update.message.reply_text(text, reply_markup=markup)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, _, ticket_str = query.data.partition(":")
    ticket = int(ticket_str)
    if not mt5.initialize():
        await query.answer("MT5 Bridge down", show_alert=True)
        return
    pos = None
    for p in mt5.positions_get() or []:
        if p.ticket == ticket:
            pos = p
            break
    if not pos:
        await query.edit_message_text(f"Ticket #{ticket} is no longer open.")
        return
    if action == "be":
        req = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "sl": pos.price_open, "tp": pos.tp}
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            await query.answer(f"Ticket #{ticket} Stop Loss moved to BE!", show_alert=True)
        else:
            await query.answer("Failed to adjust SL", show_alert=True)
    elif action == "close":
        tick = mt5.symbol_info_tick(pos.symbol)
        cp = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "price": cp,
            "deviation": 25,
            "comment": "QN-C2-Close",
        }
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            await query.edit_message_text(f"Ticket #{ticket} CLOSED via Telegram C2")
        else:
            await query.answer("Close failed", show_alert=True)
    elif action == "refresh":
        tick = mt5.symbol_info_tick(pos.symbol)
        sym = mt5.symbol_info(pos.symbol)
        curr_price = (tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask) if tick else pos.price_open
        point = sym.point if sym and sym.point else 0.00001
        drift = ((curr_price - pos.price_open) / point) if pos.type == mt5.ORDER_TYPE_BUY else ((pos.price_open - curr_price) / point)
        order_str = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        card_text = (
            f"DRIFT / DELTA ANALYSIS: #{pos.ticket}\n"
            "------------------------------------\n"
            f"Pair: {pos.symbol} ({order_str} {pos.volume}L)\n"
            f"Entry: {pos.price_open:.5f} -> Now: {curr_price:.5f}\n"
            f"Price Drift: {drift:+.1f} pts\n"
            f"Floating Delta: ${pos.profit:+.2f}\n"
            f"SL: {pos.sl:.5f} | TP: {pos.tp:.5f}\n"
            "------------------------------------"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Move to BE", callback_data=f"be:{pos.ticket}"),
                InlineKeyboardButton("Close 50%", callback_data=f"half:{pos.ticket}")
            ],
            [
                InlineKeyboardButton("Close Trade", callback_data=f"close:{pos.ticket}"),
                InlineKeyboardButton("Refresh", callback_data=f"refresh:{pos.ticket}")
            ]
        ])
        await query.edit_message_text(card_text, reply_markup=keyboard)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["status", "positions", "trades", "orders"], status_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    print("=================================================================")
    print("  QUANT NEXUS - COMMAND & CONTROL TELEGRAM BOT ACTIVE")
    print("  Listening for /status, /positions, /trades")
    print("=================================================================")
    app.run_polling()

if __name__ == "__main__":
    main()