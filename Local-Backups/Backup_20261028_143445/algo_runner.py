import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Set, Tuple

import httpx
import MetaTrader5 as mt5
from dotenv import load_dotenv

from engine_algorithmic import (
    MicrostructureEngine,
    calculate_kelly_lot_size,
    calculate_dynamic_kelly_risk,
)

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (AlgoRunner) %(message)s"
)
logger = logging.getLogger("AlgoRunner")

WATCHLIST = ["XAUUSD", "BTCUSD", "EURUSD"]
BRIDGE_WEBHOOK_URL = "http://127.0.0.1:5000/webhook"
MAGIC_NUMBER = 999101

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")

# --- Institutional Risk Controls ---
MAX_CONCURRENT_POSITIONS_PER_ASSET = 1  # Prevents position stacking
MAX_TOTAL_OPEN_RISK_USD = 1500.0        # Max aggregate floating loss cap
ORDER_EXPIRY_SECONDS = 4 * 15 * 60       # 60-minute pending TTL

SESSION_MODE = "LONDON_OR_NY"
LONDON_START_HOUR_UTC = 7
LONDON_END_HOUR_UTC = 16
NY_START_HOUR_UTC = 12
NY_END_HOUR_UTC = 21


def send_telegram_alert(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not ADMIN_TELEGRAM_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_TELEGRAM_ID, "text": message, "parse_mode": "Markdown"}
    try:
        with httpx.Client(timeout=8.0) as client:
            client.post(url, json=payload)
    except Exception as exc:
        logger.error(f"Failed to transmit Telegram alert: {exc}")


def purge_expired_pending_orders():
    pending_orders = mt5.orders_get(magic=MAGIC_NUMBER) or []
    current_epoch = time.time()

    for order in pending_orders:
        elapsed_sec = current_epoch - order.time_setup
        if elapsed_sec >= ORDER_EXPIRY_SECONDS:
            order_type_str = "BUY_LIMIT" if order.type == mt5.ORDER_TYPE_BUY_LIMIT else "SELL_LIMIT"
            cancel_request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order.ticket,
                "comment": "Algo-Order-TTL-Expired"
            }
            res = mt5.order_send(cancel_request)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                send_telegram_alert(
                    f"⏳ *PENDING ORDER CANCELLED (TTL EXPIRED)*\n"
                    f"• Ticket: `#{order.ticket}`\n"
                    f"• Asset: `{order.symbol}` ({order_type_str})\n"
                    f"• Time Elapsed: `{int(elapsed_sec // 60)} mins`"
                )


def evaluate_portfolio_heat(symbol: str) -> Tuple[bool, str]:
    """
    Blocks execution if the symbol already has an open position/order,
    or if aggregate basket drawdown exceeds MAX_TOTAL_OPEN_RISK_USD.
    """
    positions = mt5.positions_get(magic=MAGIC_NUMBER) or []
    orders = mt5.orders_get(magic=MAGIC_NUMBER) or []

    # 1. Anti-Stacking Check: Count active trades + pending orders on this symbol
    active_asset_count = sum(1 for p in positions if p.symbol.upper() == symbol.upper())
    pending_asset_count = sum(1 for o in orders if o.symbol.upper() == symbol.upper())

    if (active_asset_count + pending_asset_count) >= MAX_CONCURRENT_POSITIONS_PER_ASSET:
        return False, f"Anti-stacking active ({active_asset_count} open, {pending_asset_count} pending on {symbol})"

    # 2. Portfolio Heat Check: Aggregate floating drawdown across the entire magic number
    total_floating_loss = sum(abs(p.profit) for p in positions if p.profit < 0)
    if total_floating_loss >= MAX_TOTAL_OPEN_RISK_USD:
        return False, f"Portfolio heat cap hit (-${total_floating_loss:,.2f} >=${MAX_TOTAL_OPEN_RISK_USD:,.2f})"

    return True, "Passed"


def is_active_session() -> Tuple[bool, str]:
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()
    hour = now_utc.hour + (now_utc.minute / 60.0)

    if weekday == 5 or (weekday == 4 and hour >= 21) or (weekday == 6 and hour < 21):
        return False, "Weekend Market Closure"

    is_london = LONDON_START_HOUR_UTC <= hour < LONDON_END_HOUR_UTC
    is_ny = NY_START_HOUR_UTC <= hour < NY_END_HOUR_UTC
    is_overlap = is_london and is_ny

    if SESSION_MODE == "OVERLAP_ONLY":
        return (True, "London/NY Overlap") if is_overlap else (False, "Outside Overlap")
    elif SESSION_MODE == "LONDON_OR_NY":
        if is_overlap:
            return True, "London/NY Overlap"
        if is_london:
            return True, "London Session"
        if is_ny:
            return True, "New York Session"
        return False, "Off-Hours"
    return True, "Full Day"


def run_zero_latency_cycle():
    if not mt5.initialize():
        logger.error(f"MT5 Init failed: {mt5.last_error()}")
        return

    purge_expired_pending_orders()

    session_active, session_name = is_active_session()
    now_utc_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    if not session_active:
        logger.info(f"⏸️ [Session Gate Active] {now_utc_str} | Status: {session_name}. Waiting...")
        return

    logger.info(f"⚡ Scanning M15 Bars | Session: {session_name} ({now_utc_str})")

    with httpx.Client(timeout=4.0) as client:
        for symbol in WATCHLIST:
            active_sym = symbol
            if not mt5.symbol_select(active_sym, True):
                for sfx in [f"{symbol}m", f"{symbol}.r", f"{symbol}.pro"]:
                    if mt5.symbol_select(sfx, True):
                        active_sym = sfx
                        break

            # Run Anti-Stacking & Portfolio Heat Validation
            passed_gate, gate_reason = evaluate_portfolio_heat(active_sym)
            if not passed_gate:
                logger.debug(f"Skipping {active_sym}: {gate_reason}")
                continue

            engine = MicrostructureEngine(symbol=active_sym, timeframe=mt5.TIMEFRAME_M15, num_bars=100)
            df = engine.fetch_rates()
            if df is None:
                continue

            df = engine.compute_indicators(df)
            sig = engine.scan_microstructure_signals(df)

            if sig["action"] != "HOLD" and sig["quant_score"] >= 7.0:
                sl_dist = abs(sig["entry_price"] - sig["sl"])

                dynamic_risk_usd, km = calculate_dynamic_kelly_risk(
                    magic_number=MAGIC_NUMBER,
                    lookback_days=30,
                    default_risk_pct=0.01,
                    base_kelly_fraction=0.35,
                    min_risk_pct=0.005,
                    max_risk_pct=0.025
                )

                lot_size = calculate_kelly_lot_size(active_sym, dynamic_risk_usd, sl_dist)

                payload = {
                    "action": str(sig["action"]),
                    "symbol": str(active_sym),
                    "volume_lots": float(lot_size),
                    "price": float(sig["entry_price"]),
                    "sl": float(sig["sl"]),
                    "tp1": float(sig["tp1"]),
                    "tp2": float(sig["tp2"]),
                    "comment": f"Algo-Nexus-{sig['quant_score']}"
                }

                logger.info(f"🎯 Execution Approved on {active_sym}: {payload}")

                try:
                    res = client.post(BRIDGE_WEBHOOK_URL, json=payload)
                    if res.status_code == 200:
                        ticket = res.json().get("ticket", "LIVE")
                        alert_msg = (
                            "⚡ *ALGORITHMIC ORDER TRIGGERED*\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"• *Ticket:* `#{ticket}`\n"
                            f"• *Asset:* `{active_sym}` ({sig['action']})\n"
                            f"• *Volume:* `{lot_size} lots`\n"
                            f"• *Risk Allocated:* `${dynamic_risk_usd:,.2f}` (`{km.get('risk_pct', 1.0)}%`)\n"
                            f"• *Drawdown State:* `{km.get('throttle_state', 'NORMAL')}`\n"
                            f"• *Entry:* `{sig['entry_price']}` | *SL:* `{sig['sl']}`\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            "🛡️ *Anti-stacking locked for this symbol.*"
                        )
                        send_telegram_alert(alert_msg)
                except Exception as exc:
                    logger.error(f"Execution delivery error on {active_sym}: {exc}")


if __name__ == "__main__":
    while True:
        run_zero_latency_cycle()
        time.sleep(15)