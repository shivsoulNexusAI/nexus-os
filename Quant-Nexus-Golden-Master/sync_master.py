import json
import MetaTrader5 as mt5

with open("nexus_config.json", "r", encoding="utf-8-sig") as f:
    cfg = json.load(f)["account"]

if not mt5.initialize():
    print("[-] MT5 initialization failed:", mt5.last_error())
    exit(1)

logged_in = mt5.login(login=int(cfg["login"]), password=cfg["password"], server=cfg["server"])
if not logged_in:
    print(f"[-] MT5 Login Failed: {mt5.last_error()}")
    mt5.shutdown()
    exit(1)

acc = mt5.account_info()
print("=" * 60)
print("     SHIVSOUL 10K MASTER LEDGER SYNC COMPLETE")
print("=" * 60)
print(f"  Account Login : {acc.login}")
print(f"  Server        : {acc.server}")
print(f"  Live Balance  : ${acc.balance:,.2f}")
print(f"  Live Equity   : ${acc.equity:,.2f}")
print(f"  Free Margin   : ${acc.margin_free:,.2f}")
print(f"  Leverage      : 1:{acc.leverage}")
print("=" * 60)
mt5.shutdown()