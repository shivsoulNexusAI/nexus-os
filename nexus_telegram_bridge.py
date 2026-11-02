import time
import requests
import traceback
import MetaTrader5 as mt5
from datetime import datetime, timezone
from apex_ml_feature_engine import ApexMicrostructureML

# ==============================================================================
# TELEMETRY & DESK SPECIFICATION
# ==============================================================================
TELEGRAM_BOT_TOKEN = "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw"
PRIMARY_CHAT_ID    = "5279761713"
MT5_PATH           = r"C:\Program Files\MetaTrader 5\terminal64.exe"
ACCOUNT_LOGIN      = 278025377
ACCOUNT_SERVER     = "Exness-MT5Trial5"

SYMBOLS            = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "USDJPY"]
MAX_CONCURRENT     = 2
KRONOS_MAX_MINS    = 60.0

def send_msg(text: str, target_chat_id: str = None):
    cid = target_chat_id or PRIMARY_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=8)
        if not r.ok:
            print(f"[!] Send error: {r.status_code} -> {r.text}")
        else:
            print(f"[+] Matrix delivered to {cid}")
    except Exception as e:
        print(f"[!] Network error: {e}")

def ensure_mt5():
    if not mt5.terminal_info() or not mt5.account_info() or mt5.account_info().login != ACCOUNT_LOGIN:
        return mt5.initialize(path=MT5_PATH, login=ACCOUNT_LOGIN, server=ACCOUNT_SERVER, portable=True)
    return True

def build_status_matrix():
    if not ensure_mt5():
        return "⚠️ *MT5 Connection Error* - Unable to attach to terminal."

    acc = mt5.account_info()
    positions = mt5.positions_get() or []
    pos_count = len(positions)
    
    balance = acc.balance
    equity = acc.equity
    floating_pnl = equity - balance
    margin_free = acc.margin_free
    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    header_icon = "🟢" if floating_pnl >= 0 else "🔴"
    
    msg = (
        f"🏛️ *QUANT NEXUS APEX FUSION MATRIX*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *NAV*: `${equity:,.2f}` | *Float*: {header_icon} *${floating_pnl:+.2f}*\n"
        f"🛡️ *Free Margin*: `${margin_free:,.2f}` | *Fleet*: `{pos_count}/{MAX_CONCURRENT} Locked`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ *LIVE MARKET EXECUTIONS (LOCKED)*\n"
    )

    if not positions:
        msg += "▫️ _No active exposures. Capital 100% idle._\n"
    else:
        for p in positions:
            side = "BUY" if p.type == 0 else "SELL"
            open_dt = datetime.fromtimestamp(p.time, timezone.utc)
            duration_min = (datetime.now(timezone.utc) - open_dt).total_seconds() / 60.0
            pnl_ico = "🟢" if p.profit >= 0 else "🔴"

            msg += (
                f"- *{p.symbol}* ({side} `{p.volume:.2f}L`) | Float: {pnl_ico} *${p.profit:+.2f}*\n"
                f"  Open: `{p.price_open}` | Cur: `{p.price_current}` | Age: `{duration_min:.0f}m`\n\n"
            )

    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📡 *SCANNER FLEET (MICROSTRUCTURE ML)*\n"
    
    for sym in SYMBOLS:
        res = ApexMicrostructureML.extract_features(sym)
        if not res:
            msg += f"▫️ `{sym:<6}` | Offline\n"
            continue
        
        prob = res["probability"] * 100.0
        ofi = res["ofi"]
        sp_ratio = res["spread_ratio"]
        bias = res["bias"]
        
        is_open = any(p.symbol == sym for p in positions)
        if is_open:
            tag = "🔒 [LOCKED]"
        elif prob >= 65.0 and sp_ratio <= 2.50 and bias != "NEUTRAL":
            tag = "🎯 *SIGNAL*"
        elif prob >= 55.0:
            tag = "⚡ WARM"
        else:
            tag = "⚪ NEUTRAL"

        msg += f"#{SYMBOLS.index(sym)+1} `{sym:<6}` {tag} | P(Win): `{prob:.1f}%` | OFI: `{ofi:>+5.2f}`\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎯 *ALPHA TRIGGER*: Machine Learning Dynamic Half-Kelly Active\n"
    msg += f"⏱️ *Updated*: `{now_utc}` | 60s Cadence"
    return msg

def poll_telegram_commands():
    # 1. Flush stale updates
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except Exception:
        pass

    print("[+] Apex Institutional Telegram Bridge Initializing...")
    print("[+] Sending startup notification...")
    init_matrix = build_status_matrix()
    send_msg(init_matrix)
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    last_update_id = 0
    try:
        r = requests.get(url, params={"offset": -1}, timeout=5).json()
        if "result" in r and len(r["result"]) > 0:
            last_update_id = r["result"][-1]["update_id"]
    except Exception:
        pass

    last_auto_scan = time.time()
    print(f"[+] Apex Bridge Listening (Offset: {last_update_id}). Ready for commands...")

    while True:
        # Periodic 60-Second Auto Push
        if time.time() - last_auto_scan >= 60.0:
            print("\n[AUTO-CADENCE] Broadcasting 60s Institutional Matrix...")
            try:
                matrix_text = build_status_matrix()
                send_msg(matrix_text)
                last_auto_scan = time.time()
            except Exception as e:
                print(f"[!] Auto-push error: {e}")

        # Non-blocking Polling Loop
        try:
            resp = requests.get(url, params={"offset": last_update_id + 1, "timeout": 3}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("result", []):
                    last_update_id = item["update_id"]
                    msg = item.get("message", {}) or item.get("channel_post", {})
                    sender_chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip()

                    print(f"[CMD INCOMING] ChatID: {sender_chat_id} | Text: '{text}'")

                    norm = text.lower()
                    if any(k in norm for k in ["/status", "/scan", "/pnl", "/audit", "/pos"]):
                        print(f"[DISPATCH] Generating Matrix for {sender_chat_id}...")
                        m = build_status_matrix()
                        send_msg(m, target_chat_id=sender_chat_id)
                    elif "/ping" in norm:
                        send_msg("⚡ *Nexus Core Online*: Sub-10ms VPS Latency.", target_chat_id=sender_chat_id)
            elif resp.status_code == 409:
                print("[!] 409 Conflict: another listener active. Waiting...")
                time.sleep(3)
        except requests.exceptions.Timeout:
            pass  # Standard long-poll cycle completion
        except requests.exceptions.RequestException as re:
            time.sleep(2)
        except Exception as e:
            print(f"[!] Loop exception: {e}")

        time.sleep(0.5)

if __name__ == "__main__":
    poll_telegram_commands()
