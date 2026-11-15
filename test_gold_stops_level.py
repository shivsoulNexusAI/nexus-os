import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_HFT_278041671/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    acc = mt5.account_info()
    orders = mt5.orders_get() or []
    tick = mt5.symbol_info_tick("XAUUSD")
    sym_info = mt5.symbol_info("XAUUSD")
    
    print("=" * 85)
    print(f"HFT TERMINAL SPREAD & STOPS LEVEL AUDIT (#{acc.login})")
    print("=" * 85)
    print(f"Bid: {tick.bid:.3f} | Ask: {tick.ask:.3f} | Spread: ${(tick.ask - tick.bid):.3f}")
    print(f"Stops Level (pts) : {sym_info.stops_level} (Min distance broker requires for pending orders)")
    print(f"Point size        : {sym_info.point}")
    print(f"Min Stop Distance : ${sym_info.stops_level * sym_info.point:.3f}")
    print(f"Active Orders Count: {len(orders)}")
    for o in orders:
        o_name = "BUY_STOP" if o.type == 4 else ("SELL_STOP" if o.type == 5 else str(o.type))
        print(f"  -> #{o.ticket} {o_name} @ {o.price_open:.3f} (Magic: {o.magic}) | Comment: {o.comment}")
    mt5.shutdown()
    print("=" * 85)
else:
    print("[-] Failed to initialize Terminal 3.")