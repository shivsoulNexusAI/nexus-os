import os
import sys
import time
import logging
import asyncio
from datetime import datetime
from typing import List, Optional

import httpx
import MetaTrader5 as mt5
from dotenv import load_dotenv

# Ensure root project imports work
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app.agents.oracle import OracleAgent
from app.agents.nexus import NexusAgent
from app.core.config import settings

load_dotenv(override=True)

# ------------------------------------------------------------------------------
# 1. Configuration & Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (AutoScreener) %(message)s"
)
logger = logging.getLogger("AutoScreener")

# Target assets to monitor every cycle
WATCHLIST = ["XAUUSD", "BTCUSD", "EURUSD", "US30"]
TIMEFRAME = mt5.TIMEFRAME_M15
CHART_WIDTH = 1920
CHART_HEIGHT = 1080

SCREENSHOT_DIR = os.path.join(PROJECT_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

BRIDGE_URL = getattr(settings, "MT5_BRIDGE_URL", os.getenv("MT5_BRIDGE_URL", "http://127.0.0.1:5000/webhook"))
TELEGRAM_BOT_TOKEN = getattr(settings, "TELEGRAM_BOT_TOKEN", None) or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = getattr(settings, "ADMIN_TELEGRAM_ID", None) or os.getenv("ADMIN_TELEGRAM_ID")

MIN_CONVICTION_SCORE = 6.5
MIN_RRR = 1.5

oracle_agent = OracleAgent()
nexus_agent = NexusAgent()


# ------------------------------------------------------------------------------
# 2. Telegram Alert Dispatchers
# ------------------------------------------------------------------------------
async def send_telegram_card(text: str, photo_path: Optional[str] = None) -> None:
    """Dispatches photo cards or Markdown reports directly to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_TELEGRAM_ID:
        return

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if photo_path and os.path.exists(photo_path):
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                with open(photo_path, "rb") as img:
                    await client.post(
                        url,
                        data={"chat_id": ADMIN_TELEGRAM_ID, "caption": text, "parse_mode": "Markdown"},
                        files={"photo": img}
                    )
            else:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                await client.post(
                    url,
                    json={"chat_id": ADMIN_TELEGRAM_ID, "text": text, "parse_mode": "Markdown"}
                )
    except Exception as exc:
        logger.error(f"Failed to transmit Telegram report: {exc}")


# ------------------------------------------------------------------------------
# 3. Chart Capture Engine
# ------------------------------------------------------------------------------
def capture_chart_image(symbol: str) -> Optional[str]:
    """Ensures chart is open in MT5 and takes a high-res programmatic screenshot."""
    # Ensure symbol is selected in Market Watch
    if not mt5.symbol_select(symbol, True):
        # Fallback for Exness raw/pro suffixes (e.g. XAUUSDm)
        for sfx in [f"{symbol}m", f"{symbol}.r", f"{symbol}.pro", f"{symbol}+"]:
            if mt5.symbol_select(sfx, True):
                symbol = sfx
                break

    # Look for an existing chart window for this symbol
    charts = mt5.chart_id_list() or []
    target_chart_id = None

    for cid in charts:
        if mt5.chart_symbol(cid) == symbol:
            target_chart_id = cid
            break

    # If no chart is open, create one dynamically
    if target_chart_id is None:
        target_chart_id = mt5.chart_open(symbol, TIMEFRAME)
        time.sleep(1.0)  # Allow candles to populate

    if target_chart_id is None or target_chart_id == 0:
        logger.warning(f"Could not open chart for {symbol}")
        return None

    # Apply M15 timeframe and candlestick visual mode
    mt5.chart_set_integer(target_chart_id, mt5.CHART_MODE, mt5.CHART_CANDLE_NAMES if hasattr(mt5, "CHART_CANDLE_NAMES") else 1)
    
    file_name = f"{symbol}_{int(time.time())}.png"
    file_path = os.path.join(SCREENSHOT_DIR, file_name)

    # Capture chart directly via MT5 engine
    success = mt5.chart_screen_shot(target_chart_id, file_path, CHART_WIDTH, CHART_HEIGHT)
    if success and os.path.exists(file_path):
        return file_path

    logger.error(f"mt5.chart_screen_shot failed for {symbol}: {mt5.last_error()}")
    return None


# ------------------------------------------------------------------------------
# 4. Analysis and Execution Engine
# ------------------------------------------------------------------------------
async def process_symbol_scan(symbol: str) -> None:
    """Takes chart screenshot, analyzes via Vision + Nexus, and auto-dispatches."""
    logger.info(f"📸 Capturing {symbol} chart...")
    image_path = capture_chart_image(symbol)
    if not image_path:
        return

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        logger.info(f"🧠 Feeding {symbol} into Oracle Vision...")
        oracle_data = await oracle_agent.identify_and_analyze(image_bytes)

        logger.info(f"📐 Synthesizing Kelly allocation for {symbol}...")
        quant_signal = await nexus_agent.synthesize(oracle_data=oracle_data)

        direction_clean = quant_signal.direction.upper()
        report = quant_signal.telegram_formatted_report

        # Skip neutral / wait setups
        if "HOLD" in direction_clean or "WAIT" in direction_clean:
            logger.info(f"⏸️ {symbol}: Market condition neutral. Skipping execution.")
            return

        # Quality check
        if quant_signal.quant_score < MIN_CONVICTION_SCORE or quant_signal.risk_reward_ratio < MIN_RRR:
            logger.info(
                f"⚠️ {symbol}: Setup vetoed (Score {quant_signal.quant_score}/{MIN_CONVICTION_SCORE}, "
                f"RRR 1:{quant_signal.risk_reward_ratio:.2f})"
            )
            return

        # Passed all filters -> execute immediately via Bridge
        logger.info(f"🚀 {symbol}: Setup meets all institutional criteria! Executing on MT5...")
        order_dict = (
            quant_signal.webhook_order.model_dump()
            if hasattr(quant_signal.webhook_order, "model_dump")
            else quant_signal.webhook_order
        )

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(BRIDGE_URL, json=order_dict)

        if resp.status_code == 200:
            ticket = resp.json().get("ticket", "LIVE")
            success_caption = (
                f"⚡ *AUTONOMOUS SCREENER EXECUTION*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• *Ticket:* `#{ticket}`\n"
                f"• *Asset:* `{symbol}` ({direction_clean})\n"
                f"• *Score:* `{quant_signal.quant_score}/10`\n"
                f"• *RRR:* `1:{quant_signal.risk_reward_ratio:.2f}`\n\n"
                f"{report}\n\n"
                f"🛡️ *Trailing Guard Active (1.5R BE + 50% TP1)*"
            )
            await send_telegram_card(success_caption, photo_path=image_path)
            logger.info(f"✅ {symbol} Trade Executed! Ticket #{ticket}")
        else:
            logger.error(f"Bridge placement error: {resp.text}")

    except Exception as exc:
        logger.error(f"Error processing {symbol}: {exc}", exc_info=True)
    finally:
        # Cleanup screenshot to conserve disk storage
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass


# ------------------------------------------------------------------------------
# 5. Continuous 15-Minute Scheduling Loop
# ------------------------------------------------------------------------------
async def run_screener_loop():
    logger.info("🛰️ QUANT NEXUS AUTONOMOUS CHART SCREENER ACTIVE")
    
    if not mt5.initialize():
        logger.critical(f"Failed to connect to MT5 Terminal: {mt5.last_error()}")
        return

    acc = mt5.account_info()
    if acc:
        logger.info(f"Target Terminal Connected: Account #{acc.login} ({acc.server})")

    INTERVAL_SECONDS = 15 * 60  # 15 Minutes

    while True:
        cycle_start = time.time()
        logger.info(f"🔄 Starting scanning cycle for watchlist: {WATCHLIST}")

        for sym in WATCHLIST:
            await process_symbol_scan(sym)
            await asyncio.sleep(2)  # 2s pacing between chart captures

        elapsed = time.time() - cycle_start
        sleep_duration = max(5, INTERVAL_SECONDS - elapsed)
        logger.info(f"💤 Cycle complete in {elapsed:.1f}s. Sleeping for {sleep_duration/60:.1f} minutes...")
        await asyncio.sleep(sleep_duration)


if __name__ == "__main__":
    try:
        asyncio.run(run_screener_loop())
    except KeyboardInterrupt:
        logger.info("AutoScreener stopped by user.")
        mt5.shutdown()