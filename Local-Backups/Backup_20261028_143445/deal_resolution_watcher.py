"""
QUANTUM NEXUS // REAL-TIME DEAL RESOLUTION & TELEMETRY DISPATCHER
Monitors MT5 deal history for TP/SL hits, pushes instant PnL summaries to Telegram,
and executes immediate real-time ratchets on the Trailing Circuit Breaker floor.
"""
import time
import os
import requests
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
from trailing_circuit_breaker import TrailingCircuitBreaker

LOGIN = 278017866
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"
TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# Load credentials from .env if present
env_path = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\.env"
env_vars = {}
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip('"').strip("'")

BOT_TOKEN = env_vars.get("TELEGRAM_BOT_TOKEN", "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw")
CHAT_ID = env_vars.get("TELEGRAM_CHAT_ID", "5279761713")

def send_telegram(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, headers={"Content-Type": "application/json; charset=utf-8"}, data=json.dumps(payload).encode("utf-8"), timeout=5)
    except Exception:
        pass

def main():
    if not mt5.initialize(path=TERMINAL_PATH) or not mt5.login(login=LOGIN, password=PASSWORD, server=SERVER):
        print(f"[WATCHER] MT5 Login Failed: {mt5.last_error()}")
        return

    print("🟢 Deal Resolution Watcher Online. Monitoring deal history & dynamic floor ratchets...")
    breaker = TrailingCircuitBreaker()
    processed_deals = set()

    # Pre-populate existing history to prevent alert storms on boot
    now = datetime.now(timezone.utc)
    past_deals = mt5.history_deals_get(now - timedelta(days=2), now)
    if past_deals:
        for d in past_deals:
            processed_deals.add(d.ticket)

    while True:
        try:
            now = datetime.now(timezone.utc)
            deals = mt5.history_deals_get(now - timedelta(hours=1), now)
            if deals:
                for d in deals:
                    if d.ticket not in processed_deals and d.entry == mt5.DEAL_ENTRY_OUT:
                        processed_deals.add(d.ticket)
                        profit = d.profit

                        # Force immediate Circuit Breaker evaluation & HWM ratchet
                        eval_res = breaker.evaluate()
                        hwm = eval_res.get("hwm", breaker.hwm)
                        floor = eval_res.get("floor", breaker.current_floor)
                        buf = eval_res.get("buffer_usd", 0.0)

                        emoji = "🎯 <b>[PROFIT HARVESTED]</b>" if profit >= 0 else "🛡️ <b>[STOP MITIGATED]</b>"
                        msg = (
                            f"{emoji}\n"
                            f"• <b>Symbol</b>    : <code>{d.symbol}</code>\n"
                            f"• <b>Volume</b>    : <code>{d.volume:.2f}L</code>\n"
                            f"• <b>Exit Price</b>: <code>{d.price:.5f}</code>\n"
                            f"• <b>Net PnL</b>    : <b>${profit:+.2f} USD</b>\n"
                            f"• <b>Deal ID</b>   : #{d.ticket}\n"
                            f"• <b>Floor Ratchet</b>: Floor: <code>${floor:.2f}</code> | HWM: <code>${hwm:.2f}</code> (Buf: <code>+${buf:.2f}</code>)\n"
                            f"• <b>Time</b>      : {datetime.fromtimestamp(d.time, timezone.utc).strftime('%H:%M:%S UTC')}"
                        )
                        send_telegram(msg)
                        print(f"[WATCHER] Deal #{d.ticket} processed: ${profit:+.2f} | Floor locked at ${floor:.2f}")
        except Exception as e:
            print(f"[WATCHER] Loop error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
