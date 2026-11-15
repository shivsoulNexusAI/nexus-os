import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    orders = mt5.orders_get() or []
    print("=" * 80)
    print(f"PURGING STALE PENDING ORDERS ON ACCOUNT #{mt5.account_info().login}")
    print("=" * 80)
    for o in orders:
        if o.ticket in [2847044152, 2847056140, 2847056449] or "NEXUS_DYN_P2" in o.comment:
            req = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": o.ticket
            }
            res = mt5.order_send(req)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[+] Successfully purged Order #{o.ticket} ({o.symbol} {o.comment})")
            else:
                print(f"[-] Failed to cancel Order #{o.ticket}: {res.comment}")
    mt5.shutdown()
    print("=" * 80)
else:
    print("[-] Terminal init failed.")