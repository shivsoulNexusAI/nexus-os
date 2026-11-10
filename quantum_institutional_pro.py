# -*- coding: utf-8 -*-
"""
SHIVSOUL NEXUS // OMEGA APEX ELITE MATRIX v2.0 - FINAL PRODUCTION POLISH
- Dynamic Bias Indicators (🟢 BUY / 🔴 SELL / ⚪ FLAT)
- Asset-Normalized Pip Delta Scaling
- Monospace Column Alignment
"""
import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import httpx
import MetaTrader5 as mt5

CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\quantum_institutional_pro.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("OmegaApexPro")

MT5_PATH = r"C:\MT5_Quant_278017866\terminal64.exe"
ACCOUNT = 278017866
CADENCE = 60.0

FLEET_SYMBOLS = [
    ("BTCUSD", "M15"),
    ("XAUUSD", "M5"),
    ("EURUSD", "M15"),
    ("GBPUSD", "M15"),
    ("USDJPY", "M5"),
    ("GBPJPY", "M15")
]

def load_telegram_cfg():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("bot_token"), data.get("authorized_chat_id")
    except Exception:
        return None, None

def send_or_edit_anchor(text: str, anchor_id: int = None) -> int:
    token, chat_id = load_telegram_cfg()
    if not token or not chat_id:
        return None
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🚨 Kill T1", "callback_data": "KILL_T1"},
                {"text": "🚨 Kill T2", "callback_data": "KILL_T2"},
                {"text": "🚨 Kill T3", "callback_data": "KILL_T3"}
            ],
            [
                {"text": "🔒 Break-Even All", "callback_data": "BE_ALL"},
                {"text": "🔄 Resync Fleet", "callback_data": "SYNC"}
            ]
        ]
    }

    headers = {"Content-Type": "application/json; charset=utf-8"}

    with httpx.Client(timeout=10.0) as client:
        if anchor_id:
            edit_url = f"https://api.telegram.org/bot{token}/editMessageText"
            payload = {
                "chat_id": chat_id,
                "message_id": anchor_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard
            }
            try:
                r = client.post(edit_url, json=payload, headers=headers)
                if r.status_code == 200:
                    return anchor_id
            except Exception as e:
                log.warning("Edit failed: %s", e)

        # Fallback to dispatching new anchor message
        send_url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard
        }
        try:
            r = client.post(send_url, json=payload, headers=headers)
            if r.status_code == 200:
                res_data = r.json()
                new_id = res_data["result"]["message_id"]
                return new_id
        except Exception as e:
            log.error("Send new anchor failed: %s", e)
    return None

def compute_microstructure(symbol: str, tf_str: str):
    tf = mt5.TIMEFRAME_M15 if tf_str == "M15" else mt5.TIMEFRAME_M5
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, 14)
    if rates is None or len(rates) < 10:
        return "+0", "+0.00", 50, "FLAT", "⚪"

    closes = [r['close'] for r in rates]
    highs = [r['high'] for r in rates]
    lows = [r['low'] for r in rates]

    p_range = max(highs) - min(lows) or 1.0
    net = closes[-1] - closes[0]
    dii = net / p_range

    # Asset-calibrated delta calculation
    diff = closes[-1] - closes[-2]
    if "BTC" in symbol:
        delta_pips = int(diff)            # $1 increments for BTC
    elif "XAU" in symbol:
        delta_pips = int(diff * 10)       # 10c increments for Gold
    elif "JPY" in symbol:
        delta_pips = int(diff * 100)      # Standard pips for JPY
    else:
        delta_pips = int(diff * 10000)    # Standard pips for FX Majors (EUR, GBP)

    score = int(50 + (dii * 40))
    score = max(25, min(85, score))

    # Dynamic status indicators
    if dii >= 0.12:
        state, dot = "BUY ", "🟢"
    elif dii <= -0.12:
        state, dot = "SELL", "🔴"
    else:
        state, dot = "FLAT", "⚪"

    return f"{delta_pips:+4d}", f"{dii:+.02f}", score, state, dot

def build_matrix_dashboard():
    acc = mt5.account_info()
    positions = mt5.positions_get() or []

    total_profit = sum(p.profit for p in positions)
    active_symbols = {p.symbol for p in positions}

    lines = [
        "🔱 <b>SHIVSOUL NEXUS / OMEGA APEX ELITE MATRIX</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>NAV</b>   <code>${acc.equity:,.2f}</code>",
        f"<b>Float</b> <code>{total_profit:+.2f}</code>",
        f"<b>FreeM</b> <code>${acc.margin_free:,.2f}</code> | Fleet {len(positions)}/6",
        "<b>OMEGA-APEX-v2.0</b> | <code>100% AUTONOMOUS</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚡ <b>LIVE MARKET EXECUTIONS (LOCKED)</b>"
    ]

    if positions:
        for p in positions:
            side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
            lines.append(f"<b>{p.symbol}</b> • {side} {p.volume}L")
            lines.append(f"Float <code>{p.profit:+.2f}</code> | Open <code>{p.price_open}</code>")
    else:
        lines.append("<i>Standing by — Zero floating exposure</i>")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        # Check Macro Shock Lockout
    news_file = Path(r"C:\Quant-Nexus-Eng\news_lockout.json")
    if news_file.exists():
        try:
            n_state = json.loads(news_file.read_text(encoding="utf-8"))
            if n_state.get("quarantine_active"):
                th = n_state.get("active_threats", [{}])[0]
                lines.append(f"🎯 <b>ALPHA TRIGGER:</b> ⚠️ <code>NEWS LOCKOUT [{th.get('currency')}]</code>")
            elif n_state.get("upcoming_events"):
                up = n_state.get("upcoming_events", [{}])[0]
                lines.append(f"🎯 <b>ALPHA TRIGGER:</b> Edge Surveillance | <code>{up.get('currency')} in {up.get('mins_away')}m</code>")
            else:
                lines.append("🎯 <b>ALPHA TRIGGER:</b> Matrix Balanced | Awaiting Edge")
        except Exception:
            lines.append("🎯 <b>ALPHA TRIGGER:</b> Matrix Balanced | Awaiting Edge")
    else:
        lines.append("🎯 <b>ALPHA TRIGGER:</b> Matrix Balanced | Awaiting Edge")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📡 <b>MICROSTRUCTURE SCANNER FLEET (M15+M5 DUAL)</b>")

    for idx, (sym, tf) in enumerate(FLEET_SYMBOLS, start=1):
        delta_val, dii_val, score, state, dot = compute_microstructure(sym, tf)
        tag = "🔒 [LCK]" if sym in active_symbols else "⚡ [HUNT]"
        lines.append(f"#{idx} <b>{sym}</b> {dot} <code>{state} [{tf:<3}] {score}%</code>")
        lines.append(f"   <code>Δ:{delta_val:>5}  DII:{dii_val}</code> {tag}")

    now_utc = datetime.now(timezone.utc)
    utc_clock = now_utc.strftime("%H:%M:%S UTC")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🌎 <b>LIVE 60S CADENCE ACTIVE</b>")
    lines.append(f"⏱️ <code>{utc_clock}</code> | 🇬🇧 <code>LDN-NY (ASIA -8h15m)</code> | <code>75%</code>")

    return "\n".join(lines)

def run():
    log.info("Launching Polished ShivSoul Nexus / Omega Apex Matrix...")
    if not mt5.initialize(path=MT5_PATH):
        log.error("MT5 init failure: %s", MT5_PATH)
        return

    anchor_file = Path(r"C:\Quant-Nexus-Eng\cadence_anchor.json")
    anchor_id = None
    if anchor_file.exists():
        try:
            anchor_id = json.loads(anchor_file.read_text(encoding="utf-8")).get("message_id")
        except Exception:
            anchor_id = None

    frame = 0
    try:
        while True:
            text = build_matrix_dashboard()
            res_id = send_or_edit_anchor(text, anchor_id)
            if res_id and res_id != anchor_id:
                anchor_id = res_id
                anchor_file.write_text(json.dumps({"message_id": anchor_id}), encoding="utf-8")
                log.info("Registered new polished anchor: ID #%s", anchor_id)
            
            frame = (frame + 1) % 4
            time.sleep(CADENCE)
    except KeyboardInterrupt:
        log.info("Engine stopped by user.")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    run()