import time
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import requests
import os
from nexus_core_risk import DynamicNexusRisk

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7963283296:AAH3k1V0m1K_Jj7FqB4Q1wSg3T4lX-example")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "5849842778")

def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or "example" in TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except Exception:
        pass

def main():
    if not mt5.initialize():
        print("[-] MT5 Initialization Failed")
        return

    print("🟢 ShivSoul Deal Resolution Watcher Online. Dynamic scaling active.")
    risk_governor = DynamicNexusRisk()
    processed_deals = set()

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
                        eval_res = risk_governor.evaluate()
                        
                        emoji = "🎯 <b>[PROFIT HARVESTED]</b>" if profit >= 0 else "🛡️ <b>[STOP MITIGATED]</b>"
                        msg = (
                            f"{emoji}\n"
                            f"• <b>Symbol</b>    : <code>{d.symbol}</code>\n"
                            f"• <b>Volume</b>    : <code>{d.volume:.2f}L</code>\n"
                            f"• <b>Net PnL</b>   : <b>${profit:+.2f} USD</b>\n"
                            f"• <b>Dynamic Floor</b>: Floor: <code>${eval_res.get('floor', 0.0):,.2f}</code> | "
                            f"HWM: <code>${eval_res.get('hwm', 0.0):,.2f}</code>\n"
                            f"• <b>Time</b>      : {datetime.fromtimestamp(d.time, timezone.utc).strftime('%H:%M:%S UTC')}"
                        )
                        send_telegram(msg)
                        print(f"[WATCHER] Deal #{d.ticket} processed: ${profit:+.2f}")
        except Exception as e:
            print(f"[WATCHER] Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
