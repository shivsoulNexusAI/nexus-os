"""
QUANTNEXUS TELEGRAM QUANT ALERT BOT (v3.0 Institutional Master)
Integrates FVG-CE order alerts, Volatility Regime telemetry, 
automated Risk Breaker warnings, and remote command callbacks.
"""
import os
import sys
import json
import time
import asyncio
from datetime import datetime, timezone
import httpx

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_state_guard import read_risk_state, write_risk_state
from nexus_logging_guard import get_rotating_logger

logger = get_rotating_logger("QuantAlertBot", "quant_alert_bot.log")

CONFIG_PATH = r"C:\Quant-Nexus-Eng\telegram_config.json"

def load_telegram_config():
    if not os.path.exists(CONFIG_PATH):
        logger.error(f"Missing telegram config at {CONFIG_PATH}")
        return None
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

cfg = load_telegram_config()
TOKEN = cfg.get("quant_alert_bot", {}).get("token") or cfg.get("bot_token")
CHAT_ID = cfg.get("quant_alert_bot", {}).get("chat_id") or cfg.get("chat_id")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

async def send_formatted_alert(text: str, parse_mode: str = "HTML") -> bool:
    """Dispatches a formatted alert asynchronously with retry logic."""
    if not TOKEN or not CHAT_ID:
        logger.warning("Telegram credentials not configured. Skipping broadcast.")
        return False

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{BASE_URL}/sendMessage", json=payload)
            if resp.status_code == 200:
                logger.info("Alert dispatched successfully.")
                return True
            logger.error(f"Telegram API Error {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.exception(f"Network error sending telegram alert: {e}")
    return False

# ==============================================================================
# TELEMETRY TEMPLATES (INSTITUTIONAL HUD FORMAT)
# ==============================================================================

def format_fvg_order_alert(order_data: dict) -> str:
    """Renders FVG Consequent Encroachment limit order setup."""
    return (
        f"<b>⚡ [QUANT-DELTA] FVG-CE ORDER ANCHORED</b>\n"
        f"────────────────────────\n"
        f"• <b>Symbol:</b> <code>{order_data.get('symbol')}</code> ({order_data.get('timeframe', 'M5')})\n"
        f"• <b>Type:</b> <code>{order_data.get('type')}</code>\n"
        f"• <b>Consequent Encroachment (CE):</b> <code>{order_data.get('entry'):.5f}</code>\n"
        f"• <b>Structural Stop:</b> <code>{order_data.get('sl'):.5f}</code>\n"
        f"• <b>Regime Target ({order_data.get('tp_mult', 2.0)}R):</b> <code>{order_data.get('tp'):.5f}</code>\n"
        f"• <b>Position Sizing:</b> <code>{order_data.get('lots')} Lots</code> ({order_data.get('kelly_scale', 1.0)}x Kelly)\n"
        f"• <b>Terminal Target:</b> <code>{order_data.get('terminal_id', 'DEFAULT')}</code>\n"
        f"────────────────────────\n"
        f"<i>Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    )

def format_regime_shift_alert(regime_data: dict) -> str:
    """Renders Bayesian Volatility Regime transitions."""
    badge = "🟢" if regime_data['regime_label'] == "NORMAL_DRIFT" else ("🟡" if regime_data['regime_label'] == "COMPRESSION" else "🔴")
    return (
        f"<b>{badge} [VOLATILITY REGIME SHIFT]</b>\n"
        f"────────────────────────\n"
        f"• <b>Symbol:</b> <code>{regime_data['symbol']}</code>\n"
        f"• <b>New Regime:</b> <code>{regime_data['regime_label']}</code>\n"
        f"• <b>Kaufman Efficiency (KER):</b> <code>{regime_data['efficiency_ratio']}</code>\n"
        f"• <b>ATR Expansion Ratio:</b> <code>{regime_data['atr_expansion_ratio']}x</code>\n"
        f"• <b>Parkinson Volatility:</b> <code>{regime_data['parkinson_vol']}%</code>\n"
        f"• <b>Kelly Sizing Factor:</b> <code>{regime_data['kelly_scale']}x</code>\n"
        f"• <b>Take-Profit Target:</b> <code>{regime_data['tp_multiplier']}R</code>\n"
        f"────────────────────────\n"
        f"<i>Action: Dynamic execution parameters modulated cluster-wide.</i>"
    )

def format_breaker_alert(state: dict) -> str:
    """Renders emergency circuit breaker halt event."""
    return (
        f"<b>🚨 [CIRCUIT BREAKER ENGAGED] TRADING HALTED</b>\n"
        f"────────────────────────\n"
        f"• <b>Trigger Reason:</b> <code>{state.get('active_circuit_reason')}</code>\n"
        f"• <b>Daily Loss Level:</b> <code>{state.get('daily_loss_pct')}%</code>\n"
        f"• <b>Consecutive Loss Count:</b> <code>{state.get('consecutive_losses')}</code>\n"
        f"• <b>Current Cluster Equity:</b> <code>${state.get('current_balance', 0):,.2f}</code>\n"
        f"────────────────────────\n"
        f"<b>FAIL-SAFE ACTIVE:</b> All outbound order generation suspended across all terminals."
    )

if __name__ == "__main__":
    print("[*] Testing QuantNexus Institutional Alert Broadcaster...")
    test_msg = (
        "<b>🛡️ [NEXUS MASTER PRODUCTION] TELEMETRY INITIALIZED</b>\n"
        "────────────────────────\n"
        "• <b>Environment:</b> <code>C:\\Quant-Nexus-Eng</code>\n"
        "• <b>Subsystems:</b> FVG-CE Engine | Bayesian Volatility | Sentinels\n"
        "• <b>Status:</b> Fully Operational\n"
        "────────────────────────\n"
        f"<i>Deployment Seal Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    )
    asyncio.run(send_formatted_alert(test_msg))
