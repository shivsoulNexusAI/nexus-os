import os, sys, time, socket, atexit, logging, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TG_TOKEN", "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw")
CHAT_ID = os.getenv("TG_CHAT_ID", "5279761713")
LOCK_PORT = 49200

# Dynamically overridden by $env:C2_BASE detected in pre-flight
C2_BASE = os.getenv("C2_BASE", "http://127.0.0.1:8080")
C2_TELEMETRY = f"{C2_BASE}/api/telemetry"
C2_RADAR = f"{C2_BASE}/api/radar"
C2_EXECUTE = f"{C2_BASE}/api/execute"
C2_FLATTEN = f"{C2_BASE}/api/flatten"
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

FLEET_SYMBOLS = ["BTCUSD", "GBPUSD", "XAUUSD", "EURUSD", "USDJPY"]
CADENCE = 60.0
TRIGGER_COOLDOWN = 900
BURST_MIN_DWELL = 0.30

logging.basicConfig(
    format="[%(asctime)s UTC] [%(levelname)s] [%(threadName)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("nexus_cadence.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
logging.Formatter.converter = time.gmtime
log = logging.getLogger("NexusEngine")

state_lock = threading.Lock()
stop_event = threading.Event()
refresh_event = threading.Event()

ACTIVE_MID = None
LAST_TEXT = None
_burst_block_until = 0.0
GATE_THRESHOLD = 75
EXECUTED_TRIGGERS = {}
IN_FLIGHT = set()

session = requests.Session()
_ad = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)
session.mount("http://", _ad)
session.mount("https://", _ad)
pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="Radar")

# ---------- Telegram Transport ----------
def tg_call(method, payload=None, timeout=6.0):
    for attempt in (1, 2):
        try:
            r = session.post(f"{TG_API}/{method}", json=payload or {}, timeout=timeout)
            j = r.json()
            if not j.get("ok") and j.get("error_code") == 429 and attempt == 1:
                time.sleep(min(float(j.get("parameters", {}).get("retry_after", 1)), 10))
                continue
            return j
        except Exception as e:
            log.warning(f"Telegram '{method}' failed: {e}")
            return {"ok": False, "description": str(e)}
    return {"ok": False, "description": "retry exhausted"}

def tg_once(method, payload, timeout=2.0):
    try:
        return session.post(f"{TG_API}/{method}", json=payload or {}, timeout=timeout).json()
    except Exception as e:
        return {"ok": False, "description": str(e)}

def keyboard(gate, confirm_flatten=False):
    if confirm_flatten:
        return {"inline_keyboard": [[
            {"text": "⚠️ CONFIRM FLATTEN", "callback_data": "flatten_confirm"},
            {"text": "✖ Cancel", "callback_data": "flatten_cancel"}]]}
    g75 = "🎯 Gate 75% ●" if gate == 75 else "🎯 Gate 75%"
    g80 = "🎯 Gate 80% ●" if gate == 80 else "🎯 Gate 80%"
    return {"inline_keyboard": [
        [{"text": "📊 /status", "callback_data": "cmd_status"},
         {"text": "🛰 /scan", "callback_data": "cmd_scan"}],
        [{"text": g75, "callback_data": "set_gate_75"},
         {"text": g80, "callback_data": "set_gate_80"},
         {"text": "🚨 /flatten", "callback_data": "cmd_flatten"}]]}

# ---------- Data Fetching ----------
def fetch_telemetry_safe():
    try:
        r = session.get(C2_TELEMETRY, timeout=3.0)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

def fetch_radar_safe(sym, tf):
    try:
        r = session.get(C2_RADAR, params={"symbol": sym, "tf": tf}, timeout=7.0)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

def footer(gate):
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    zws = "\u200b" * (int(time.time()) % 4 + 1)
    return f"🟢 <b>LIVE 60S CADENCE ACTIVE</b>\n⏱️ Updated: {now} UTC | Gate: {gate}%{zws}"

def build_matrix_view():
    with state_lock:
        gate = GATE_THRESHOLD
    data = fetch_telemetry_safe()
    if not data or not data.get("account"):
        return ("🏛️ <b>NEXUS HEDGE DESK | OMEGA APEX ELITE MATRIX</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🔴 <b>C2 OFFLINE</b> — no telemetry\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" + footer(gate)), []

    acc = data.get("account", {})
    equity = acc.get("equity", 0.0)
    balance = acc.get("balance", 0.0)
    realized = data.get("realized_pnl", 0.0)
    floating = data.get("floating_pnl", round(equity - balance, 2))
    free_mgn = acc.get("free_margin", acc.get("margin_free", round(balance + floating * 0.98, 2)))
    
    cb = data.get("circuit_breaker", {})
    cb_rem = cb.get("buffer", max(0.0, data.get("cb_limit", 300.0) + realized + min(0.0, floating)))

    pos = data.get("positions", [])
    open_syms = [p["symbol"].upper() for p in pos]
    be = "🔒 LOCKED BE" if any(p.get("floating_pnl", 0) > 15 for p in pos) else "DYNAMIC"

    L = [
        "🏛️ <b>NEXUS HEDGE DESK | OMEGA APEX ELITE MATRIX</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>NAV:</b>      <code>${equity:,.2f}</code> | <b>Float:</b> <code>${floating:+,.2f} ({be})</code>",
        f"<b>Realized:</b> <code>${realized:+,.2f}</code> | <b>Buffer:</b> <code>${cb_rem:,.2f} to CB</code>",
        f"<b>Free Mgn:</b> <code>${free_mgn:,.2f}</code> | <b>Fleet:</b> <code>{len(open_syms)}/5 Active</code>",
        "<b>Engine:</b>   <code>OMEGA-APEX-v2.0</code> | <b>Execution:</b> <code>100% AUTONOMOUS</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if pos:
        L.append("⚡ <b>ACTIVE POSITIONS (CORRELATION SHIELD)</b>")
        for p in pos:
            p_type = "SELL" if "SELL" in str(p.get("type", "")).upper() or str(p.get("type")) == "1" else "BUY"
            L.append(f"• <b>{p['symbol']}</b> [<code>{p_type}</code>] {p['volume']:.2f}L | "
                     f"Float: <code>${p['floating_pnl']:+,.2f}</code>\n"
                     f"  Open: <code>{p['entry_price']:.4f}</code> | SL: <code>{p['current_sl']:.4f}</code> (🔒 PROTECTED)")
        L.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    L.append("📡 <b>MICROSTRUCTURE SCANNER FLEET (M15+M5 DUAL)</b>")
    futs = {s: (pool.submit(fetch_radar_safe, s, "M15"), pool.submit(fetch_radar_safe, s, "M5"))
            for s in FLEET_SYMBOLS}
    triggers = []
    for idx, sym in enumerate(FLEET_SYMBOLS, 1):
        try:
            r15 = futs[sym][0].result(timeout=2.0)
        except Exception:
            r15 = {}
        try:
            r5 = futs[sym][1].result(timeout=2.0)
        except Exception:
            r5 = {}

        p15, p5 = r15.get("setup_probability", 50.0), r5.get("setup_probability", 50.0)
        best, prob, tf = (r15, p15, "M15") if p15 >= p5 else (r5, p5, "M5")
        bias = best.get("bias", "NEUTRAL")
        delta = int(best.get("bar_delta", 0))
        dii = float(best.get("dii", 0.0))
        atr_ok = best.get("atr_status") == "PERMITTED"
        emoji = "🟢" if bias == "BUY" else ("🔴" if bias == "SELL" else "⚪")
        in_trade = sym in open_syms
        tag = "🔒 [IN-TRADE]" if in_trade else "⚡ [HUNTING]"
        L.append(f"#{idx} <b>{sym}</b>  {emoji} <b>{bias} [{tf}] ({prob:.0f}%)</b> | "
                 f"<code>Δ:{delta:+d}</code> <code>DII:{dii:+.2f}</code> {tag}")
        if not in_trade and prob >= gate and bias in ("BUY", "SELL") and atr_ok:
            triggers.append({"symbol": sym, "bias": bias, "prob": prob, "gate": gate})

    L.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    L.append(footer(gate))
    return "\n".join(L), triggers

# ---------- Visual Dissolve Transition Engine ----------
def make_dissolve_frame(old_text):
    out = []
    for line in old_text.split("\n"):
        if "NEXUS HEDGE DESK" in line:
            out.append("🏛️ <b>NEXUS HEDGE DESK | ⚡ SYNCHRONIZING FLEET MATRIX...</b>")
        elif "LIVE 60S CADENCE ACTIVE" in line:
            out.append("📡 ◌ ◌ ◌ <b>SCANNING ORDERFLOW RADAR [BURST CYCLE]...</b>")
        elif "Updated:" in line:
            out.append("⏱️ <i>Fetching live delta &amp; tick imbalances...</i>")
        else:
            out.append(line)
    return "\n".join(out)

def begin_burst(kb):
    global _burst_block_until
    with state_lock:
        cur, last = ACTIVE_MID, LAST_TEXT
    if not cur or not last or time.time() < _burst_block_until:
        return None
    res = tg_once("editMessageText", {
        "chat_id": CHAT_ID,
        "message_id": cur,
        "text": make_dissolve_frame(last),
        "parse_mode": "HTML",
        "reply_markup": kb
    })
    if res.get("ok"):
        _burst_block_until = time.time() + 4.0
        return time.time()
    if res.get("error_code") == 429:
        ra = float(res.get("parameters", {}).get("retry_after", 5))
        _burst_block_until = time.time() + ra + 5.0
    return None

def publish_card(text, kb, t_sweep=None):
    global ACTIVE_MID, LAST_TEXT
    if t_sweep:
        rem = BURST_MIN_DWELL - (time.time() - t_sweep)
        if rem > 0:
            time.sleep(rem)
    with state_lock:
        cur = ACTIVE_MID
    if cur:
        res = tg_call("editMessageText", {
            "chat_id": CHAT_ID,
            "message_id": cur,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": kb
        })
        if res.get("ok") or "not modified" in str(res.get("description", "")).lower():
            with state_lock:
                LAST_TEXT = text
            log.info(f"Card refreshed #{cur}")
            return
    res = tg_call("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": kb
    })
    if res.get("ok"):
        with state_lock:
            ACTIVE_MID = res["result"]["message_id"]
            LAST_TEXT = text
        if cur:
            tg_call("deleteMessage", {"chat_id": CHAT_ID, "message_id": cur})
        log.info(f"Matrix anchored at bottom: #{ACTIVE_MID}")

def drop_card():
    global ACTIVE_MID
    with state_lock:
        mid, ACTIVE_MID = ACTIVE_MID, None
    if mid:
        tg_call("deleteMessage", {"chat_id": CHAT_ID, "message_id": mid})

def cadence_broadcaster():
    log.info("Broadcaster active.")
    while not stop_event.is_set():
        t0 = time.time()
        t_sweep = None
        try:
            with state_lock:
                gate = GATE_THRESHOLD
            t_sweep = begin_burst(keyboard(gate))
            text, triggers = build_matrix_view()
            with state_lock:
                gate = GATE_THRESHOLD
            publish_card(text, keyboard(gate), t_sweep)
            for t in triggers:
                dispatch_trigger(t)
        except Exception as e:
            log.error(f"Broadcaster cycle error: {e}", exc_info=True)
            if t_sweep:
                with state_lock:
                    cur, last = ACTIVE_MID, LAST_TEXT
                if cur and last:
                    tg_once("editMessageText", {
                        "chat_id": CHAT_ID,
                        "message_id": cur,
                        "text": last,
                        "parse_mode": "HTML",
                        "reply_markup": keyboard(GATE_THRESHOLD)
                    })
        wait = max(5.0, CADENCE - (time.time() - t0))
        refresh_event.wait(wait)
        refresh_event.clear()

# ---------- Autonomous Execution ----------
def dispatch_trigger(t):
    key = f"{t['symbol']}_{t['bias']}"
    now = time.time()
    with state_lock:
        if key in IN_FLIGHT or now - EXECUTED_TRIGGERS.get(key, 0) <= TRIGGER_COOLDOWN:
            return
        IN_FLIGHT.add(key)
        EXECUTED_TRIGGERS[key] = now
    threading.Thread(target=execute_trigger, args=(t, key), name=f"Exec-{key}", daemon=True).start()

def execute_trigger(t, key):
    try:
        log.info(f"Executing: {key} @ {t['prob']:.0f}%")
        try:
            res = session.get(C2_EXECUTE, params={"symbol": t["symbol"], "bias": t["bias"]},
                              timeout=8.0).json()
        except Exception as ex:
            res = {"success": False, "error": str(ex)}

        if res.get("success"):
            alert = (
                "⚡ <b>AUTONOMOUS ALPHA TRADE FILLED</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Asset:</b> <code>{t['symbol']}</code>\n"
                f"• <b>Side:</b> <b>{t['bias']}</b> @ <code>${res.get('price', 0):,.3f}</code>\n"
                f"• <b>Ticket:</b> <code>#{res.get('ticket')} ({res.get('volume')}L)</code>\n"
                f"• <b>Probability:</b> <b>{t['prob']:.0f}%</b> (Gated >= {t['gate']}%)\n"
                f"• <b>SL:</b> <code>${res.get('sl', 0):,.3f}</code> | <b>TP:</b> <code>${res.get('tp', 0):,.3f}</code>\n"
                "• <b>Status:</b> 🔒 <b>ACTIVE IN POSITION</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        else:
            with state_lock:
                EXECUTED_TRIGGERS[key] = time.time() - TRIGGER_COOLDOWN + 120
            alert = ("⚠️ <b>AUTONOMOUS EXECUTION NOTICE</b>\n"
                     f"Asset: <b>{t['symbol']}</b> ({t['bias']} @ {t['prob']:.0f}%)\n"
                     f"Detail: <code>{res.get('error', 'Execution rejected')}</code>")
        tg_call("sendMessage", {"chat_id": CHAT_ID, "text": alert, "parse_mode": "HTML"})
        drop_card()
        refresh_event.set()
    finally:
        with state_lock:
            IN_FLIGHT.discard(key)

# ---------- Command & Callback Handling ----------
def command_listener():
    log.info("Listener online.")
    offset = None
    while not stop_event.is_set():
        try:
            params = {"timeout": 20, "allowed_updates": ["message", "callback_query"]}
            if offset:
                params["offset"] = offset
            res = tg_call("getUpdates", params, timeout=25.0)
            if not res.get("ok"):
                time.sleep(2); continue
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                if "callback_query" in u:
                    cq = u["callback_query"]
                    data = cq.get("data", "")
                    cid = str(cq.get("message", {}).get("chat", {}).get("id"))
                    if cid == CHAT_ID:
                        threading.Thread(target=handle_callback, args=(cq["id"], data),
                                         daemon=True).start()
                elif "message" in u:
                    m = u["message"]
                    text = str(m.get("text", "")).strip()
                    if str(m.get("chat", {}).get("id")) == CHAT_ID and text.startswith("/"):
                        threading.Thread(target=handle_command, args=(text.split()[0].split("@")[0],),
                                         daemon=True).start()
        except Exception as e:
            log.warning(f"Polling warning: {e}")
            time.sleep(2)

def handle_callback(cq_id, data):
    global GATE_THRESHOLD
    tg_call("answerCallbackQuery", {"callback_query_id": cq_id})
    if data in ("set_gate_75", "set_gate_80"):
        with state_lock:
            GATE_THRESHOLD = int(data[-2:])
    elif data == "cmd_flatten":
        with state_lock:
            mid = ACTIVE_MID
        if mid:
            tg_call("editMessageReplyMarkup", {"chat_id": CHAT_ID, "message_id": mid,
                                               "reply_markup": keyboard(0, confirm_flatten=True)})
        return
    elif data == "flatten_confirm":
        try:
            r = session.get(C2_FLATTEN, timeout=6.0)
            tg_call("sendMessage", {"chat_id": CHAT_ID, "parse_mode": "HTML",
                    "text": f"🚨 <b>FLATTEN</b> sent — C2 HTTP {r.status_code}"})
        except Exception as e:
            tg_call("sendMessage", {"chat_id": CHAT_ID, "parse_mode": "HTML",
                    "text": f"🚨 <b>FLATTEN FAILED</b>: <code>{e}</code>"})
        drop_card()
    refresh_event.set()

def handle_command(cmd):
    if cmd in ("/status", "/scan"):
        refresh_event.set()

# ---------- Supervisor ----------
def main():
    if not TELEGRAM_BOT_TOKEN:
        sys.exit("Missing TG_TOKEN env var.")

    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        guard.bind(("127.0.0.1", LOCK_PORT))
        guard.listen(1)
        atexit.register(guard.close)
    except OSError:
        sys.exit(f"Port {LOCK_PORT} locked. Another instance is running.")

    tg_call("deleteWebhook", {"drop_pending_updates": True})

    targets = {"Broadcaster": cadence_broadcaster, "CommandListener": command_listener}
    workers = {n: threading.Thread(target=f, name=n, daemon=True) for n, f in targets.items()}
    for w in workers.values():
        w.start()
    log.info("[+] Nexus Cadence Engine initialized and supervised.")

    try:
        while not stop_event.is_set():
            time.sleep(5)
            for n, w in list(workers.items()):
                if not w.is_alive():
                    log.error(f"Thread '{n}' died. Respawning.")
                    workers[n] = threading.Thread(target=targets[n], name=n, daemon=True)
                    workers[n].start()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        stop_event.set(); refresh_event.set()

if __name__ == "__main__":
    main()



