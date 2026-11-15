import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    pos = mt5.positions_get(ticket=2827676341)
    if pos:
        p = pos[0]
        # Current entry: 1.33381, Current mark ~1.32689
        proposed_sl = 1.32850  # Locks in +53.1 pips ($15.93 guaranteed on 0.03L)
        if p.sl > proposed_sl:
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": p.ticket,
                "symbol": p.symbol,
                "sl": proposed_sl,
                "tp": p.tp
            }
            res = mt5.order_send(req)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[+] Trailing Stop updated to {proposed_sl} (+53.1 pips locked in)!")
            else:
                print(f"[-] Trailing modification failed: {res.comment}")
        else:
            print(f"[i] SL is already tighter than proposed trail: {p.sl}")
    mt5.shutdown()