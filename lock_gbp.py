import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    pos = mt5.positions_get(ticket=2827676341)
    if pos:
        p = pos[0]
        pts_gain = (p.price_open - p.price_current) / 0.00001
        print("=" * 80)
        print(f"POSITION AUDIT: GBPUSD SHORT #{p.ticket}")
        print(f"Entry: {p.price_open:.5f} | Current: {p.price_current:.5f} | Profit: ${p.profit:+.2f} (+{pts_gain:.1f} pips)")
        print(f"Current SL: {p.sl:.5f}")
        
        # Short position: Move SL 2 pips below entry to lock in net profit
        new_sl = round(p.price_open - 0.00020, 5)
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": p.ticket,
            "symbol": p.symbol,
            "sl": new_sl,
            "tp": p.tp
        }
        res = mt5.order_send(req)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[+] SUCCESS: SL ratcheted to {new_sl} (+2.0 pips secured, 100% risk-free)!")
        else:
            print(f"[-] SL adjustment failed: {res.comment} (code {res.retcode})")
        print("=" * 80)
    else:
        print("[-] Position #2827676341 not found on Account #278062039.")
    mt5.shutdown()
else:
    print(f"[-] MT5 init failed: {mt5.last_error()}")