import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_HFT_278041671/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    orders = mt5.orders_get() or []
    for o in orders:
        res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[+] Purged orphan order #{o.ticket}")
    mt5.shutdown()