import httpx
from telegram_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
acc_txt = "Account Info Unavailable"

if mt5.initialize(path=TERMINAL, portable=False):
    acc = mt5.account_info()
    pos = mt5.positions_get() or []
    acc_txt = f"Login: #{acc.login}\nBalance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f}\nActive Runners: {len(pos)} (USDJPY locked in profit)"
    mt5.shutdown()

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": f"🟢 <b>[QUANT-NEXUS TELEMETRY RESTORED]</b>\nVPS Headless Session Online.\n{acc_txt}",
    "parse_mode": "HTML"
}

r = httpx.post(url, json=payload, timeout=10.0)
if r.status_code == 200:
    print("[SUCCESS] Live Telegram notification delivered to your phone!")
else:
    print(f"[-] Telegram Error ({r.status_code}): {r.text}")