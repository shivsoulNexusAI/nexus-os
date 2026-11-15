import MetaTrader5 as mt5

APEX_TERMINAL = r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe"
if mt5.initialize(path=APEX_TERMINAL, portable=False, timeout=10000):
    t_info = mt5.terminal_info()
    a_info = mt5.account_info()
    print("=" * 80)
    print("APEX SATELLITE (PID 956) EXECUTION CAPABILITIES")
    print("=" * 80)
    print(f"Account Login       : #{a_info.login}")
    print(f"Trade Allowed (Acc) : {a_info.trade_allowed}")
    print(f"Trade Expert (Acc)  : {a_info.trade_expert}")
    print(f"Trade Allowed (Term): {t_info.trade_allowed} (Must be True for EAs/Daemons)")
    print(f"Connected to Broker : {t_info.connected}")
    print("=" * 80)
    mt5.shutdown()
else:
    print(f"[-] Init failed: {mt5.last_error()}")