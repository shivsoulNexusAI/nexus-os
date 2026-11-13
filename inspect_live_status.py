import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Pending_278041169/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=True):
    acc = mt5.account_info()
    pos = mt5.positions_get() or []
    orders = mt5.orders_get() or []
    
    print("=" * 80)
    print(f"Account #{acc.login} ({acc.server})")
    print(f"Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Margin Free: ${acc.margin_free:,.2f}")
    print(f"Active Positions : {len(pos)}")
    for p in pos:
        side = "BUY" if p.type == 0 else "SELL"
        gain_pts = (p.price_current - p.price_open) if p.type == 0 else (p.price_open - p.price_current)
        print(f"  -> POS #{p.ticket} | {p.symbol:<7} {side:<4} {p.volume:.2f}L | Open: {p.price_open:.5f} | Mark: {p.price_current:.5f} | SL: {p.sl:.5f} | Gain: {gain_pts:+.5f} | PnL: ${p.profit:+.2f}")
        
    print(f"Working Orders   : {len(orders)}")
    for o in orders:
        ot = "BUY_STOP" if o.type == 4 else ("SELL_STOP" if o.type == 5 else str(o.type))
        print(f"  -> ORD #{o.ticket} | {o.symbol:<7} {ot:<9} {o.volume_current:.2f}L @ {o.price_open:.5f} | SL: {o.sl:.5f} | Tag: {o.comment}")
    mt5.shutdown()
    print("=" * 80)
else:
    print("[-] MT5 Init failed.")