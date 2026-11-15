import MetaTrader5 as mt5

APEX_TERMINAL = r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe"
if mt5.initialize(path=APEX_TERMINAL, portable=False, timeout=10000):
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "US30", "XAUUSD"]
    print("=" * 85)
    print("ENABLING MARKET WATCH SYMBOLS ON APEX SATELLITE (#278062038)")
    print("=" * 85)
    for sym in symbols:
        sel = mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        info = mt5.symbol_info(sym)
        if sel and tick and info:
            print(f"[+] {sym:<7} Subscribed | Bid: {tick.bid:<9} Ask: {tick.ask:<9} | TradeMode: {info.trade_mode}")
        else:
            print(f"[-] {sym:<7} Subscription failed or offline.")
    mt5.shutdown()
    print("=" * 85)
else:
    print(f"[-] Failed to connect: {mt5.last_error()}")