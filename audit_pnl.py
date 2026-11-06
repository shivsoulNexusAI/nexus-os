import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe", portable=True):
    print("[-] MT5 Init Failed:", mt5.last_error())
    exit()

mt5.login(login=278025377, server="Exness-MT5Trial5")

a = mt5.account_info()
utc_now = datetime.now(timezone.utc)
from_dt = utc_now - timedelta(hours=6)
deals = [d for d in (mt5.history_deals_get(from_dt, utc_now) or []) if d.entry == 1]
realized_pnl = sum(d.profit for d in deals)

print("-" * 52)
print("Account:         " + str(a.login) + " (" + str(a.server) + ")")
print("Balance:         $" + f"{a.balance:,.2f}")
print("Equity:          $" + f"{a.equity:,.2f}")
print("6h Realized PnL: $" + f"{realized_pnl:+,.2f}" + " (" + str(len(deals)) + " closed deals)")
print("-" * 52)

mt5.shutdown()
