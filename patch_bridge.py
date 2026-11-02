import os

bridge_code = """# -*- coding: utf-8 -*-
import time
import requests
import traceback
import MetaTrader5 as mt5
from datetime import datetime, timezone
from apex_ml_feature_engine import ApexMicrostructureML

# ==============================================================================
# TELEMETRY & DESK SPECIFICATION (ACCOUNT: 278029146)
# ==============================================================================
TELEGRAM_BOT_TOKEN = "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw"
PRIMARY_CHAT_ID    = "5279761713"
MT5_PATH           = r"C:\\Program Files\\MetaTrader 5\\terminal64.exe"
ACCOUNT_LOGIN      = 278029146
ACCOUNT_SERVER     = "Exness-MT5Trial5"
ACCOUNT_PASSWORD   = "H@ngkook3695"

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
            print(f"[+] Delivered to {cid}")
    except Exception as e:
        print(f"[!] Network error: {e}")

def ensure_mt5():
    if not mt5.terminal_info() or not mt5.account_info() or mt5.account_info().login != ACCOUNT_LOGIN:
        return mt5.initialize(path=MT5_PATH, login=ACCOUNT_LOGIN, password=ACCOUNT_PASSWORD, server=ACCOUNT_SERVER, portable=True)
    return True

def build_status_matrix():
    if not ensure_mt5():
        return "\\u26A0\\uFE0F *MT5 Connection Error* - Unable to attach to 10K desk terminal."

    acc = mt5.account_info()
    positions = mt5.positions_get() or []
    pos_count = len(positions)
    
    balance = acc.balance
    equity = acc.equity
    floating_pnl = equity - balance
    margin_free = acc.margin_free
    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    header_icon = "\\U0001F7E2" if floating_pnl >= 0 else "\\U0001F534"
    
    msg = (
        f"\\U0001F3DB *QUANT NEXUS APEX FUSION MATRIX*\\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        f"\\U0001F4B0 *NAV*: `${equity:,.2f}` | *Float*: {header_icon} *${floating_pnl:+.2f}*\\n"
        f"\\U0001F6E1\\uFE0F *Free Margin*: `${margin_free:,.2f}` | *Fleet*: `{pos_count}/{MAX_CONCURRENT} Locked`\\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
        f"\\u26A1 *LIVE MARKET EXECUTIONS (LOCKED)*\\n"
    )

    if not positions:
        msg += "\\u25FD _No active exposures. Capital 100% idle._\\n"
    else:
        for p in positions:
            side = "BUY" if p.type == 0 else "SELL"
            open_dt = datetime.fromtimestamp(p.time, timezone.utc)
            duration_min = (datetime.now(timezone.utc) - open_dt).total_seconds() / 60.0
            pnl_ico = "\\U0001F7E2" if p.profit >= 0 else "\\U0001F534"

            msg += (
                f"- *{p.symbol}* ({side} `{p.volume:.2f}L`) | Float: {pnl_ico} *${p.profit:+.2f}*\\n"
                f"  Open: `{p.price_open}` | Cur: `{p.price_current}` | Age: `{duration_min:.0f}m`\\n\\n"
            )

    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
    msg += f"\\U0001F4E1 *SCANNER FLEET (MICROSTRUCTURE ML)*\\n"
    
    for sym in SYMBOLS:
        res = ApexMicrostructureML.extract_features(sym)
        if not res:
            msg += f"\\u25FD `{sym:<6}` | Offline\\n"
            continue
        
        prob = res["probability"] * 100.0
        ofi = res["ofi"]
        sp_ratio = res["spread_ratio"]
        bias = res["bias"]
        
        is_open = any(p.symbol == sym for p in positions)
        if is_open:
            tag = "\\U0001F512 [LOCKED]"
        elif prob >= 65.0 and sp_ratio <= 2.50 and bias != "NEUTRAL":
            tag = "\\U0001F3AF *SIGNAL*"
        elif prob >= 55.0:
            tag = "\\u26A1 WARM"
        else:
            tag = "\\u26AA NEUTRAL"

        msg += f"#{SYMBOLS.index(sym)+1} `{sym:<6}` {tag} | P(Win): `{prob:.1f}%` | OFI: `{ofi:>+5.2f}`\\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
    msg += f"\\U0001F3AF *ALPHA TRIGGER*: Machine Learning Dynamic Half-Kelly Active\\n"
    msg += f"\\u23F1\\uFE0F *Updated*: `{now_utc}` | 60s Cadence"
    return msg

def poll_telegram_commands():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except Exception:
        pass

    print("[+] Apex Institutional Telegram Bridge Initializing on 10K Desk...")
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
    print(f"[+] Clean UTF-8 Telemetry Ready on Account 278029146. Polling commands...")

    while True:
        if time.time() - last_auto_scan >= 60.0:
            try:
                matrix_text = build_status_matrix()
                send_msg(matrix_text)
                last_auto_scan = time.time()
            except Exception as e:
                print(f"[!] Auto-push error: {e}")

        try:
            resp = requests.get(url, params={"offset": last_update_id + 1, "timeout": 3}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("result", []):
                    last_update_id = item["update_id"]
                    msg = item.get("message", {}) or item.get("channel_post", {})
                    sender_chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip()

                    norm = text.lower()
                    if any(k in norm for k in ["/status", "/scan", "/pnl", "/audit", "/pos"]):
                        m = build_status_matrix()
                        send_msg(m, target_chat_id=sender_chat_id)
                    elif "/ping" in norm:
                        send_msg("\\u26A1 *Nexus Core Online*: Sub-10ms VPS Latency.", target_chat_id=sender_chat_id)
        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            print(f"[!] Polling loop exception: {e}")

        time.sleep(0.5)

if __name__ == '__main__':
    poll_telegram_commands()
"""

with open(r"C:\Quant-Nexus-Eng\nexus_telegram_bridge.py", "w", encoding="utf-8") as f:
    f.write(bridge_code)

print("✅ nexus_telegram_bridge.py successfully written with clean UTF-8 escaping!")
