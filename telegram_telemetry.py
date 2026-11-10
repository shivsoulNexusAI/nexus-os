import json
import logging
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = "C:\\Quant-Nexus-Prod\\core\\telegram_config.json"

def _load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"[!] Could not load telegram_config.json: {e}")
        return None

def send_raw_alert(html_text: str) -> bool:
    cfg = _load_config()
    if not cfg or not cfg.get("enabled", True):
        return False
    
    bot_token = cfg.get("bot_token")
    chat_id = cfg.get("chat_id")
    if not bot_token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html_text,
        "parse_mode": "HTML"
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.status == 200
    except Exception as e:
        logging.error(f"[!] Telemetry send failed: {e}")
        return False

def alert_order_fill(ticket, symbol, direction, lots, price, sl, tp, prob=None):
    prob_str = f" | Prob: <b>{prob:.1f}%</b>" if prob else ""
    card = (
        f"🎯 <b>NEXUS ALPHA EXECUTION FILL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Ticket: <code>#{ticket}</code>\n"
        f"• Pair: <b>{symbol}</b> ({direction})\n"
        f"• Size: <code>{lots} Lots</code>{prob_str}\n"
        f"• Entry: <code>{price}</code>\n"
        f"• Stop Loss: <code>{sl}</code>\n"
        f"• Target TP: <code>{tp}</code>\n"
        f"• Time: <code>{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</code>"
    )
    return send_raw_alert(card)

def alert_breakeven_locked(ticket, symbol, new_sl, open_price, profit_usd):
    card = (
        f"🛡️ <b>RISK DEFENSE: BREAKEVEN LOCKED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Ticket: <code>#{ticket}</code> ({symbol})\n"
        f"• SL Ratchet: <code>{new_sl}</code> (Risk-Free)\n"
        f"• Open Price: <code>{open_price}</code>\n"
        f"• Floating PnL: <b>+${profit_usd:,.2f}</b>\n"
        f"• Rule: +1.0R Threshold Secured"
    )
    return send_raw_alert(card)

def alert_partial_tp_hit(ticket, symbol, close_lots, realized_usd, remaining_lots):
    card = (
        f"💰 <b>PROFIT HARVEST: +1.8R TARGET</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Ticket: <code>#{ticket}</code> ({symbol})\n"
        f"• Harvested: <code>{close_lots} Lots</code> (50% Scale-out)\n"
        f"• Realized: <b>+${realized_usd:,.2f}</b>\n"
        f"• Remaining: <code>{remaining_lots} Lots</code> Runner Active"
    )
    return send_raw_alert(card)

def alert_circuit_breaker(old_regime, new_regime, equity, floor, action_taken):
    emoji = "🚨" if "LOCKOUT" in new_regime else "⚠️" if "CAUTION" in new_regime else "🟢"
    card = (
        f"{emoji} <b>CIRCUIT BREAKER REGIME SHIFT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Previous: <code>{old_regime}</code>\n"
        f"• Active Regime: <b>{new_regime}</b>\n"
        f"• Current Equity: <b>${equity:,.2f}</b>\n"
        f"• Risk Floor: <code>${floor:,.2f}</code>\n"
        f"• Action: <b>{action_taken}</b>\n"
        f"• Timestamp: <code>{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</code>"
    )
    return send_raw_alert(card)