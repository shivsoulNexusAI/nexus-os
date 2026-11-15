import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False):
    orders = mt5.orders_get() or []
    purged = 0
    for o in orders:
        if o.ticket < 2855700000:
            res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[+] Purged legacy order #{o.ticket} ({o.symbol})")
                purged += 1
    print(f"Total legacy orders cleared: {purged}")
    mt5.shutdown()
else:
    print("[-] MT5 Init failed.")