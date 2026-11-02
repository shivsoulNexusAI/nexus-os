import os
import sys
import time
import sqlite3
import logging
import MetaTrader5 as mt5
from dotenv import load_dotenv

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

load_dotenv(override=True)
DB_PATH = os.path.join(BASE_DIR, "quant_metrics.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("OutcomeResolver")

def resolve_pending_signals():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Query active signals awaiting market resolution
    cursor.execute("""
        SELECT signal_id, asset, direction, entry_price
        FROM signal_telemetry
        WHERE outcome = 'PENDING'
    """)
    pending_signals = cursor.fetchall()

    if not pending_signals:
        conn.close()
        return

    for sig_id, asset, direction, entry_price in pending_signals:
        tick = mt5.symbol_info_tick(asset)
        sym_info = mt5.symbol_info(asset)
        if not tick or not sym_info:
            continue

        point = sym_info.point
        current_bid = tick.bid
        current_ask = tick.ask

        # Standard institutional risk distances matching execution parameters
        sl_dist = 1500 * point if "XAU" in asset else 150 * point
        tp_dist = sl_dist * 2.0  # 1:2 R:R baseline target

        is_buy = direction.upper() in ("BUY", "LONG", "BULLISH")
        sl_price = entry_price - sl_dist if is_buy else entry_price + sl_dist
        tp_price = entry_price + tp_dist if is_buy else entry_price - tp_dist

        resolved_outcome = None

        if is_buy:
            if current_bid >= tp_price:
                resolved_outcome = "WIN"
            elif current_bid <= sl_price:
                resolved_outcome = "LOSS"
        else:
            if current_ask <= tp_price:
                resolved_outcome = "WIN"
            elif current_ask >= sl_price:
                resolved_outcome = "LOSS"

        if resolved_outcome:
            cursor.execute("""
                UPDATE signal_telemetry
                SET outcome = ?
                WHERE signal_id = ?
            """, (resolved_outcome, sig_id))
            conn.commit()
            logger.info(f"🎯 Signal {sig_id} ({asset} {direction}) resolved to: {resolved_outcome}")

    conn.close()

def main_loop():
    if not mt5.initialize():
        logger.error("Failed to initialize MT5 for outcome resolver.")
        sys.exit(1)

    logger.info("📡 Quant Nexus Post-Trade Outcome Resolver online.")
    try:
        while True:
            resolve_pending_signals()
            time.sleep(15)
    except KeyboardInterrupt:
        logger.info("Resolver daemon stopped.")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main_loop()
