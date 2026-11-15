import MetaTrader5 as mt5

SLEEVES = [
    ("T1", "Apex Crypto Core",  r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe", 278062038, r"H@ngkook3695", "Exness-MT5Trial5"),
    ("T2", "FX Majors Sleeve",  r"C:\MT5_Pending_278041169\terminal64.exe",                     278062039, r"H@ngkook3695", "Exness-MT5Trial5"),
    ("T3", "Gold HFT Sleeve",   r"C:\MT5_HFT_278041671\terminal64.exe",                         278062042, r"H@ngkook3695", "Exness-MT5Trial5"),
]

print("=" * 88)
print(f"{'SLEEVE':<8} {'ACCOUNT':<11} {'CONNECTED':<11} {'ALGO_TRADING':<14} {'API_LOCK':<10} {'PING(ms)':<10} {'EQUITY'}")
print("=" * 88)

for sid, name, path, login, pwd, srv in SLEEVES:
    if not mt5.initialize(path=path, login=login, password=pwd, server=srv):
        print(f"{sid:<8} #{login:<10} {'OFFLINE':<11} {'IPC_ERROR':<14} {'-':<10} {'-':<10} {mt5.last_error()}")
        continue

    term = mt5.terminal_info()
    acc  = mt5.account_info()

    conn_str = "ONLINE" if (term and term.connected) else "DISCONNECTED"
    algo_str = "ENABLED (GREEN)" if (term and term.trade_allowed) else "DISABLED (RED)"
    api_str  = "BLOCKED" if (term and term.tradeapi_disabled) else "ALLOWED"
    ping_ms  = f"{term.ping_last / 1000.0:.1f}" if (term and term.ping_last) else "0.0"
    eq_str   = f"${acc.equity:,.2f}" if acc else "$0.00"

    print(f"{sid:<8} #{login:<10} {conn_str:<11} {algo_str:<14} {api_str:<10} {ping_ms:<10} {eq_str}")
    mt5.shutdown()

print("=" * 88)
