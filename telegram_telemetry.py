import json
import os
import threading
import urllib.parse
import urllib.request

CONFIG_FILE = "telegram_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"bot_token": "", "chat_id": "", "enabled": False}

def save_config(bot_token: str, chat_id: str, enabled: bool = True):
    config = {
        "bot_token": bot_token.strip(),
        "chat_id": str(chat_id).strip(),
        "enabled": enabled
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    return config

def _send_http_post(token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Sentinel-Nexus/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        return False

def send_telegram_alert(message: str, force_sync: bool = False):
    """
    Sends structured push notifications to your Telegram channel/chat.
    Dispatched on a background daemon thread to eliminate execution latency.
    """
    cfg = load_config()
    if not cfg.get("enabled") or not cfg.get("bot_token") or not cfg.get("chat_id"):
        return False

    if force_sync:
        return _send_http_post(cfg["bot_token"], cfg["chat_id"], message)

    t = threading.Thread(
        target=_send_http_post,
        args=(cfg["bot_token"], cfg["chat_id"], message),
        daemon=True
    )
    t.start()
    return True

# Institutional Alert Formatters
def notify_order_filled(symbol, order_type, lots, entry, sl, tp, confluence, setup_name):
    msg = (
        f"⚡ <b>SENTINEL OMEGA: ORDER EXECUTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Symbol:</b> {symbol} | <b>Action:</b> {order_type}\n"
        f"<b>Volume:</b> {lots:.2f} Lots\n"
        f"<b>Fill Price:</b> <code>{entry:.5f}</code>\n"
        f"<b>Stop Loss:</b> <code>{sl:.5f}</code>\n"
        f"<b>Take Profit:</b> <code>{tp:.5f}</code>\n"
        f"<b>Confluence:</b> {confluence:.1f}%\n"
        f"<b>PD Model:</b> {setup_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Autonomous 1.0R Breakeven Armed</i>"
    )
    send_telegram_alert(msg)

def notify_breakeven_locked(symbol, ticket, new_sl, current_profit):
    msg = (
        f"🔒 <b>RISK DEFENSE: BREAKEVEN LOCKED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Symbol:</b> {symbol} (Ticket #{ticket})\n"
        f"<b>Stop Loss Moved To:</b> <code>{new_sl:.5f}</code>\n"
        f"<b>Floating Gain:</b> +${current_profit:.2f} USD\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ <i>Downside Risk Neutralized (Free Trade)</i>"
    )
    send_telegram_alert(msg)
