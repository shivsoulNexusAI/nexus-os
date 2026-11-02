import os
import uuid
import sqlite3
import requests
from dotenv import load_dotenv
import signature_engine
import matrix_resolver
import regime_engine
import mtf_engine

load_dotenv(override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
DB_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot\quant_metrics.db"

def init_signal_telemetry_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_telemetry (
            signal_id TEXT PRIMARY KEY,
            asset TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            signature TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            outcome TEXT DEFAULT 'PENDING'
        )
    """)
    conn.commit()
    conn.close()

def broadcast_signal_with_alpha_badge(
    asset: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    trade_volume: float = 0.01,
    quant_score: float = 95.0,
    timeframe: str = "M15",
    explicit_signature: str = None,
    regime_data: dict = None,
    mtf_data: dict = None
) -> bool:
    init_signal_telemetry_table()
    signal_id = f"SIG-{uuid.uuid4().hex[:8].upper()}"

    if explicit_signature:
        sig = explicit_signature
    else:
        try:
            sig = signature_engine.build_confluence_signature(asset, timeframe)
        except Exception:
            sig = f"{timeframe}_BASE_MOMENTUM"

    alpha_badge_text = matrix_resolver.format_alpha_badge(asset, timeframe, sig)

    if regime_data is None:
        try:
            regime_data = regime_engine.evaluate_market_regime(asset)
        except Exception:
            regime_data = {
                "regime_state": "STANDARD_CONSOLIDATION",
                "position_multiplier": 1.0,
                "warning": "ℹ️ Standard risk parameters applied."
            }

    if mtf_data is None:
        try:
            mtf_data = mtf_engine.validate_mtf_alignment(asset, direction, entry_price)
        except Exception:
            mtf_data = {
                "badge_status": "⚪ NEUTRAL CONFLUENCE",
                "h4_trend": "NEUTRAL",
                "d1_trend": "NEUTRAL",
                "warnings": [],
                "bonus_reasons": []
            }

    mtf_details = ""
    if mtf_data.get("warnings"):
        mtf_details = f"• *Warning*: 🚨 _{mtf_data['warnings'][0]}_\n"
    elif mtf_data.get("bonus_reasons"):
        mtf_details = f"• *Confluence*: 🎯 _{mtf_data['bonus_reasons'][0]}_\n"

    mtf_section = (
        f"🔭 *Multi-Timeframe Alignment (D1 / H4 / {timeframe}):*\n"
        f"• *Status*: `{mtf_data['badge_status']}`\n"
        f"• *H4 Trend*: `{mtf_data['h4_trend']}` | *D1 Trend*: `{mtf_data['d1_trend']}`\n"
        f"{mtf_details}"
    )

    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)
    planned_rr = round(reward / risk, 2) if risk > 0 else 2.0
    action_emoji = "🟢 LONG" if direction.upper() in ("BUY", "LONG", "BULLISH") else "🔴 SHORT"

    message = (
        f"⚡ *QUANT NEXUS - INSTITUTIONAL EXECUTION SIGNAL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• *ID*: `{signal_id}`\n"
        f"• *Asset*: `{asset}` ({timeframe})\n"
        f"• *Action*: *{action_emoji}*\n"
        f"• *Execution Entry*: `{entry_price:.2f}`\n"
        f"• *Stop Loss*: `{stop_loss:.2f}`\n"
        f"• *Take Profit*: `{take_profit:.2f}`\n"
        f"• *Calculated Volume*: `{trade_volume:.2f} Lots`\n"
        f"• *Planned R:R*: `1:{planned_rr}`\n"
        f"• *Effective Quant Score*: `{quant_score:.1f}/100`\n"
        f"• *Pattern Signature*: `{sig}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{mtf_section}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 *Macro Regime Context:*\n"
        f"• *State*: `{regime_data['regime_state']}`\n"
        f"• *Risk Sizing Scale*: `{int(regime_data['position_multiplier'] * 100)}%`\n"
        f"• *Advisory*: _{regime_data['warning']}_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{alpha_badge_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ *Execution Status*: Guard Active"
    )

    # Persist signal metadata for community voting
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO signal_telemetry (signal_id, asset, timeframe, signature, direction, entry_price)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (signal_id, asset, timeframe, sig, direction, entry_price))
    conn.commit()
    conn.close()

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram token or chat ID missing. Alert printed to console:\n")
        print(message)
        return False

    # Attach interactive reaction inline buttons
    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "👍 Upvote (0)", "callback_data": f"vote:up:{signal_id}"},
                {"text": "👎 Downvote (0)", "callback_data": f"vote:down:{signal_id}"}
            ]
        ]
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "reply_markup": inline_keyboard
    }

    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code == 200:
            print(f"✅ Institutional Signal ({signal_id}) broadcasted with inline buttons.")
            return True
        else:
            print(f"❌ Telegram API Error ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Dispatch failed: {e}")
        return False

if __name__ == "__main__":
    broadcast_signal_with_alpha_badge(
        asset="XAUUSD",
        direction="BUY",
        entry_price=2684.50,
        stop_loss=2675.00,
        take_profit=2705.00,
        trade_volume=0.03,
        quant_score=85.0,
        timeframe="M15",
        explicit_signature="M15_BULLISH_ENGULFING+FVG+VWAP_RETEST"
    )
