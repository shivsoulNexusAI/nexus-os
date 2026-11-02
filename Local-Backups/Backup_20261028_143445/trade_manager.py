import os
import sys
import time
import logging
import requests
import MetaTrader5 as mt5
from dotenv import load_dotenv

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

load_dotenv(override=True)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TradeManager")

def notify_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")

def trail_positions_to_breakeven():
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        return

    for pos in positions:
        ticket = pos.ticket
        symbol = pos.symbol
        pos_type = pos.type  # 0 = POSITION_TYPE_BUY, 1 = POSITION_TYPE_SELL
        open_price = pos.price_open
        current_sl = pos.sl
        tp = pos.tp

        if current_sl == 0.0:
            continue

        sym_info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if not sym_info or not tick:
            continue

        point = sym_info.point
        buffer_pts = 10 * point  # 1 pip / 10 point buffer to cover commissions

        # --- LONG (BUY) POSITIONS ---
        if pos_type == mt5.POSITION_TYPE_BUY:
            initial_risk = open_price - current_sl
            if initial_risk <= 0:
                continue

            target_1r = open_price + initial_risk
            breakeven_sl = round(open_price + buffer_pts, sym_info.digits)

            # Check if 1:1 R:R achieved and SL is still below entry
            if tick.bid >= target_1r and current_sl < breakeven_sl:
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "symbol": symbol,
                    "sl": breakeven_sl,
                    "tp": tp
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"🛡️ Position #{ticket} ({symbol} BUY) moved to BREAKEVEN at {breakeven_sl}")
                    notify_telegram(
                        f"🛡️ *QUANT NEXUS - RISK-FREE PROTECTION*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• *Ticket*: `#{ticket}`\n"
                        f"• *Asset*: `{symbol}` (BUY)\n"
                        f"• *Milestone*: `1:1 R:R Achieved`\n"
                        f"• *New Stop Loss*: `{breakeven_sl:.2f}` (Breakeven + Buffer)\n"
                        f"• *Status*: Trade is now zero-risk."
                    )
                else:
                    logger.warning(f"Failed to modify ticket #{ticket}: {res.comment} (code {res.retcode})")

        # --- SHORT (SELL) POSITIONS ---
        elif pos_type == mt5.POSITION_TYPE_SELL:
            initial_risk = current_sl - open_price
            if initial_risk <= 0:
                continue

            target_1r = open_price - initial_risk
            breakeven_sl = round(open_price - buffer_pts, sym_info.digits)

            # Check if 1:1 R:R achieved and SL is still above entry
            if tick.ask <= target_1r and current_sl > breakeven_sl:
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "symbol": symbol,
                    "sl": breakeven_sl,
                    "tp": tp
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"🛡️ Position #{ticket} ({symbol} SELL) moved to BREAKEVEN at {breakeven_sl}")
                    notify_telegram(
                        f"🛡️ *QUANT NEXUS - RISK-FREE PROTECTION*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• *Ticket*: `#{ticket}`\n"
                        f"• *Asset*: `{symbol}` (SELL)\n"
                        f"• *Milestone*: `1:1 R:R Achieved`\n"
                        f"• *New Stop Loss*: `{breakeven_sl:.2f}` (Breakeven - Buffer)\n"
                        f"• *Status*: Trade is now zero-risk."
                    )
                else:
                    logger.warning(f"Failed to modify ticket #{ticket}: {res.comment} (code {res.retcode})")

def main():
    if not mt5.initialize():
        logger.error(f"MT5 Init failed: {mt5.last_error()}")
        sys.exit(1)

    logger.info("🛡️ Quant Nexus Dynamic Stop-Loss & Breakeven Manager online.")
    try:
        while True:
            trail_positions_to_breakeven()
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Trade manager stopping...")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
