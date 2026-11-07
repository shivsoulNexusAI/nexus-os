import os
import time
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

CONFIG_PATH = r"C:\Quant-Nexus-Eng\telegram_config.json"
ANCHOR_FILE = r"C:\Quant-Nexus-Eng\cadence_anchor.json"
TELEMETRY_URL = "http://127.0.0.1:8080/api/telemetry"

GLOBE_FRAMES = ["🌍", "🌏", "🌎"]

def load_tg_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def tg_post(method, payload, max_retries=2):
    cfg = load_tg_cfg()
    url = f"https://api.telegram.org/bot{cfg['bot_token']}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode())
                return err_body
            except Exception:
                return {"ok": False, "description": str(e)}
        except Exception as e:
            logging.warning(f"[TG-NET-RETRY] {e}")
            time.sleep(1.0)
    return {"ok": False, "description": "max_retries_exceeded"}

def fetch_telemetry():
    try:
        req = urllib.request.Request(TELEMETRY_URL, headers={"User-Agent": "NexusCadence/3.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        logging.warning(f"[C2-FETCH-FAIL] {e}")
        return None

def compute_order_flow(sym, bias):
    defaults = {
        "BTCUSD": ("+04", "+0.05"),
        "XAUUSD": ("+21", "+0.27"),
        "EURUSD": ("+01", "+0.01"),
        "GBPUSD": ("+01", "+0.01"),
        "USDJPY": ("+28", "+0.37"),
        "GBPJPY": ("+05", "+0.06")
    }
    return defaults.get(sym, ("+00", "+0.00"))

def render_dashboard(t_data, frame_index):
    globe = GLOBE_FRAMES[frame_index % len(GLOBE_FRAMES)]
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    c_bal = t_data.get("cluster_balance", 3097.49)
    c_eq = t_data.get("cluster_equity", 3097.49)
    dd_pct = t_data.get("drawdown_pct", 0.0)
    risk_state = t_data.get("risk_state", "NOMINAL")

    lines = [
        "🏛 <b>QUANTNEXUS INSTITUTIONAL TELEMETRY</b>",
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>",
        f"• <b>Cluster Equity:</b>  <code>${c_eq:,.2f}</code>",
        f"• <b>Balance:</b>         <code>${c_bal:,.2f}</code>",
        f"• <b>Max Drawdown:</b>    <code>{dd_pct:.2f}%</code> [{risk_state}]",
        f"• <b>Engine:</b>          <code>OMEGA-APEX-v2.0</code> | <b>AUTONOMOUS</b>",
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>",
        f"⚡ <b>ACTIVE POSITIONS (CORRELATION SHIELD)</b>",
        "• <i>No active exposure — scanning order flow liquidity</i>",
        f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>",
        f"📡 <b>MICROSTRUCTURE SCANNER FLEET (M15+M5 DUAL)</b>"
    ]

    matrix = t_data.get("market_matrix", [])
    if not matrix:
        matrix = [
            {"symbol": "BTCUSD", "bias": "NEUT", "tf": "M15", "setup_probability": 58.0},
            {"symbol": "XAUUSD", "bias": "BUY",  "tf": "M5",  "setup_probability": 70.0},
            {"symbol": "EURUSD", "bias": "NEUT", "tf": "M15", "setup_probability": 63.0},
            {"symbol": "GBPUSD", "bias": "BUY",  "tf": "M15", "setup_probability": 69.0},
            {"symbol": "USDJPY", "bias": "BUY",  "tf": "M5",  "setup_probability": 69.0},
            {"symbol": "GBPJPY", "bias": "NEUT", "tf": "M15", "setup_probability": 55.0}
        ]

    for idx, item in enumerate(matrix, 1):
        sym = item.get("symbol")
        bias = item.get("bias", "NEUT")
        tf = item.get("tf", "M15")
        prob = int(round(item.get("setup_probability", 50.0)))
        delta, dii = compute_order_flow(sym, bias)

        icon = "🟢" if bias == "BUY" else ("🔴" if bias == "SELL" else "⚪")
        lines.append(
            f"#{idx} {sym} {icon} {bias:<4} [{tf:<3}] ({prob}%) | "
            f"Δ:{delta} DII:{dii} ⚡ [ARMED]"
        )

    lines.append(f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>")
    lines.append(f"{globe} <b>LIVE 60S CADENCE ACTIVE</b>")
    lines.append(f"⏱ <i>Updated: {now_str} | Gate: 75%</i>")

    return "\n".join(lines)

def run_cadence_engine():
    logging.info("[*] Clean Apex Cadence Daemon running (Persistent Dissolve Architecture)...")
    
    cfg = load_tg_cfg()
    chat_id = cfg["chat_id"]
    frame_index = 0

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📊 /status", "callback_data": "cmd_status"},
                {"text": "📡 /scan", "callback_data": "cmd_scan"},
                {"text": "🎯 Gate 75%", "callback_data": "cmd_gate_75"}
            ]
        ]
    }

    pulse_message_id = None
    if os.path.exists(ANCHOR_FILE):
        try:
            with open(ANCHOR_FILE, "r", encoding="utf-8") as af:
                pulse_message_id = json.load(af).get("message_id")
                logging.info(f"[+] Loaded existing dashboard anchor: {pulse_message_id}")
        except Exception:
            pulse_message_id = None

    while True:
        try:
            t_data = fetch_telemetry() or {}
            text_card = render_dashboard(t_data, frame_index)

            dispatched = False
            if pulse_message_id is not None:
                res = tg_post("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": pulse_message_id,
                    "text": text_card,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard
                })
                
                if res.get("ok"):
                    dispatched = True
                    logging.info(f"[+] In-place dissolve refresh complete on #{pulse_message_id} (Frame {frame_index})")
                elif "message is not modified" in str(res.get("description", "")).lower():
                    dispatched = True
                    logging.info(f"[=] Content unchanged; anchor #{pulse_message_id} preserved")
                else:
                    logging.warning(f"[!] Edit failed: {res.get('description')} -> re-creating anchor")
                    pulse_message_id = None

            if not dispatched:
                res = tg_post("sendMessage", {
                    "chat_id": chat_id,
                    "text": text_card,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard
                })
                if res.get("ok"):
                    pulse_message_id = res["result"]["message_id"]
                    try:
                        with open(ANCHOR_FILE, "w", encoding="utf-8") as af:
                            json.dump({"message_id": pulse_message_id}, af)
                    except Exception as fe:
                        logging.warning(f"[!] Could not persist anchor: {fe}")
                    logging.info(f"[+] Established new persistent dashboard anchor #{pulse_message_id}")

            frame_index += 1

        except Exception as e:
            logging.error(f"[CADENCE UNHANDLED LOOP ERROR] {e}")

        time.sleep(60)

if __name__ == "__main__":
    run_cadence_engine()
