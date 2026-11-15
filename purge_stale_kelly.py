import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if not mt5.initialize(path=TERMINAL, portable=False):
    exit(1)

TARGET_STALE = [2827673298, 2827680633]

for ticket in TARGET_STALE:
    req = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": ticket,
        "comment": "CANCEL_STALE_KELLY"
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[+] Successfully purged stale order #{ticket}")
    else:
        err = res.comment if res else mt5.last_error()
        print(f"[-] Failed to purge #{ticket}: {err}")

mt5.shutdown()