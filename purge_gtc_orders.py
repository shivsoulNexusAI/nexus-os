import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False):
    orders = mt5.orders_get() or []
    print(f"Purging {len(orders)} stale GTC orders on #278062039...")
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
    mt5.shutdown()