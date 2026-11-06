import MetaTrader5 as mt5
import time

login = 278020233
password = "H@ngkook3695"
server = "Exness-MT5Trial5"

if not mt5.initialize():
    print("[-] MT5 initialization failed")
    exit(1)

if not mt5.login(login=login, password=password, server=server):
    print("[-] MT5 Login Failed:", mt5.last_error())
    mt5.shutdown()
    exit(1)

time.sleep(2)
acc = mt5.account_info()
if acc is not None:
    print(f"[+] SYNC SUCCESSFUL!")
    print(f"    Account:  {acc.login}")
    print(f"    Server:   {acc.server}")
    print(f"    Balance:  ${acc.balance:,.2f}")
    print(f"    Equity:   ${acc.equity:,.2f}")
    print(f"    Margin:   ${acc.margin:,.2f}")
    print(f"    Free Mgn: ${acc.margin_free:,.2f}")
    print(f"    Leverage: 1:{acc.leverage}")
else:
    print("[-] Could not retrieve account_info")
mt5.shutdown()
