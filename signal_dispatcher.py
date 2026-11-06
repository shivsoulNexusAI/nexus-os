import telegram_telemetry
import time
import logging
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [DISPATCHER] %(message)s"
)

TELEMETRY_URL = "http://127.0.0.1:8080/api/telemetry"
EXECUTE_URL = "http://127.0.0.1:8080/api/execute"
MAX_FLEET_SLOTS = 4
MIN_SETUP_PROBABILITY = 75.0
POLL_INTERVAL_SEC = 20
SYMBOL_COOLDOWN_SEC = 300  # 5-minute cooldown per symbol after execution attempt

# Track execution timestamps: symbol -> unix timestamp
execution_cooldowns = {}

def get_telemetry():
    try:
        req = urllib.request.Request(TELEMETRY_URL, headers={"User-Agent": "QuantNexusDispatcher/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logging.warning(f"Telemetry poll failed: {e}")
    return None

def execute_signal(symbol, bias):
    params = urllib.parse.urlencode({"symbol": symbol, "bias": bias})
    url = f"{EXECUTE_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QuantNexusDispatcher/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            return res_body
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return err_body
        except Exception:
            return {"success": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def clean_sym_root(s):
    s = str(s).upper()
    for suffix in ["M", ".A", "#", ".RAW", ".PRO", ".C"]:
        if s.endswith(suffix):
            return s[:-len(suffix)]
    return s

def run_dispatcher():
    logging.info("[+] QuantNexus Alpha Signal Dispatcher online.")
    logging.info(f"[*] Targeting: Max Slots={MAX_FLEET_SLOTS} | Min Prob={MIN_SETUP_PROBABILITY}% | Interval={POLL_INTERVAL_SEC}s")

    while True:
        try:
            data = get_telemetry()
            if not data:
                time.sleep(POLL_INTERVAL_SEC)
                continue

            active_positions = data.get("active_fleet_positions", [])
            open_count = len(active_positions)
            mc_regime = data.get("monte_carlo", {}).get("regime", "UNKNOWN")

            if mc_regime == "RED_LOCKOUT":
                logging.warning(f"Circuit Breaker RED_LOCKOUT. Auto-dispatch suspended. Open slots: {open_count}/{MAX_FLEET_SLOTS}")
                time.sleep(POLL_INTERVAL_SEC)
                continue

            if open_count >= MAX_FLEET_SLOTS:
                # Fleet is fully saturated; idle cleanly
                time.sleep(POLL_INTERVAL_SEC)
                continue

            slots_available = MAX_FLEET_SLOTS - open_count
            now = time.time()

            # Active symbols in inventory
            active_symbols = {clean_sym_root(p.get("symbol", "")) for p in active_positions}

            # Evaluate market matrix candidates
            matrix = data.get("market_matrix", [])
            candidates = []

            for item in matrix:
                sym = item.get("symbol", "")
                sym_root = clean_sym_root(sym)
                bias = item.get("bias", "NEUTRAL")
                prob = float(item.get("setup_probability", 0.0))
                atr_status = item.get("atr_status", "VETO_LOCKOUT")
                signal_type = item.get("signal", "")

                # 1. Skip if already held
                if sym_root in active_symbols:
                    continue

                # 2. Skip if in post-execution cooldown
                last_exec = execution_cooldowns.get(sym_root, 0)
                if (now - last_exec) < SYMBOL_COOLDOWN_SEC:
                    continue

                # 3. Filter institutional edge requirements
                if atr_status != "PERMITTED":
                    continue
                if bias not in ["BUY", "SELL"]:
                    continue
                if prob < MIN_SETUP_PROBABILITY:
                    continue

                candidates.append({
                    "symbol": sym,
                    "sym_root": sym_root,
                    "bias": bias,
                    "prob": prob,
                    "signal": signal_type
                })

            if candidates:
                # Rank highest probability first
                candidates.sort(key=lambda x: x["prob"], reverse=True)
                
                # Dispatch up to available slot capacity
                for cand in candidates[:slots_available]:
                    sym = cand["symbol"]
                    sym_root = cand["sym_root"]
                    bias = cand["bias"]
                    prob = cand["prob"]
                    sig = cand["signal"]

                    logging.info(f"[ALPHA-TRIGGER] Qualified Setup: {bias} {sym} ({prob}% | {sig}) -> Dispatching...")
                    res = execute_signal(sym, bias)

                    execution_cooldowns[sym_root] = now

                    if res.get("success"):
                        ticket = res.get("ticket")
                        price = res.get("price")
                        sl = res.get("sl")
                        tp = res.get("tp")
                        vol = res.get("volume")
                        logging.info(f"[ORDER-FILLED] #{ticket} {bias} {vol}L {sym} @ {price} | SL: {sl} | TP: {tp}")
                        try:
                            telegram_telemetry.alert_order_fill(
                                ticket=ticket,
                                symbol=sym,
                                direction=bias,
                                lots=vol,
                                price=price,
                                sl=sl,
                                tp=tp,
                                prob=prob
                            )
                        except Exception as tg_err:
                            logging.warning(f"Telegram fill alert failed: {tg_err}")
                        # Update local slot count
                        slots_available -= 1
                        if slots_available <= 0:
                            break
                    else:
                        err = res.get("error") or res.get("comment") or "Unknown"
                        logging.warning(f"[DISPATCH-REJECTED] {bias} {sym}: {err}")

        except Exception as e:
            logging.error(f"Dispatcher cycle exception: {e}")

        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    run_dispatcher()
