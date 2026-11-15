import MetaTrader5 as mt5

apex_path = r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe"
if mt5.initialize(path=apex_path, portable=False, timeout=10000):
    acc = mt5.account_info()
    pos = mt5.positions_get() or []
    orders = mt5.orders_get() or []
    print("=" * 80)
    print(f"[+] APEX SATELLITE (PID 956) ACTIVE LOGIN: #{acc.login} ({acc.server})")
    print(f"    Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f}")
    print(f"    Runners: {len(pos)} | Pending: {len(orders)}")
    print("=" * 80)
    mt5.shutdown()
else:
    print(f"[-] Could not connect to Apex Satellite: {mt5.last_error()}")