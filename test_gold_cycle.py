import MetaTrader5 as mt5
from gold_hft_straddle_daemon import sync_gold_straddle, TERMINAL_PATH, SYMBOL

if mt5.initialize(path=TERMINAL_PATH, portable=True):
    print("=" * 80)
    print("EXECUTING DIRECT sync_gold_straddle() PASS")
    print("=" * 80)
    sync_gold_straddle()
    orders = mt5.orders_get(symbol=SYMBOL) or []
    print(f"Active Orders Placed: {len(orders)}")
    for o in orders:
        ot = "BUY_STOP" if o.type == 4 else ("SELL_STOP" if o.type == 5 else str(o.type))
        print(f"  -> #{o.ticket} {ot} {o.volume_current:.2f}L @ {o.price_open:.3f} | SL: {o.sl:.3f} | TP: {o.tp:.3f}")
    mt5.shutdown()
    print("=" * 80)
else:
    print(f"[-] Init failed: {mt5.last_error()}")