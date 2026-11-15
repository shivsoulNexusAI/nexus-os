import MetaTrader5 as mt5
import time

terminal_path = r"C:/MT5_Pending_278041169/terminal64.exe"
print(f"Attempting to launch and connect to: {terminal_path}")

# Initialize with portable=True and extended timeout
init_ok = mt5.initialize(path=terminal_path, portable=True, timeout=30000)
if not init_ok:
    print(f"[-] Portable launch failed: {mt5.last_error()}. Retrying standard mode...")
    init_ok = mt5.initialize(path=terminal_path, portable=False, timeout=30000)

if init_ok:
    acc = mt5.account_info()
    print(f"[+] SUCCESS: Connected to #{acc.login} ({acc.server})")
    print(f"    Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f}")
    mt5.shutdown()
else:
    print(f"[-] Still failed: {mt5.last_error()}")