import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    acc = mt5.account_info()
    positions = mt5.positions_get() or []
    orders = mt5.orders_get() or []
    
    print("=" * 80)
    print(f"SILO 2 PRODUCTION TEST: #{acc.login} ({acc.server})")
    print(f"Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Margin Free: ${acc.margin_free:,.2f}")
    print(f"Open Positions : {len(positions)}")
    for p in positions:
        print(f"  -> POS #{p.ticket} | {p.symbol} {'BUY' if p.type==0 else 'SELL'} {p.volume:.2f}L @ {p.price_open:.5f} | Mark: {p.price_current:.5f} | SL: {p.sl:.5f} | PnL: ${p.profit:+.2f}")
    print(f"Pending Orders : {len(orders)}")
    for o in orders:
        ot = "BUY_STOP" if o.type == 4 else ("SELL_STOP" if o.type == 5 else str(o.type))
        print(f"  -> ORD #{o.ticket} | {o.symbol} {ot} {o.volume_current:.2f}L @ {o.price_open:.5f} | Tag: {o.comment}")
    mt5.shutdown()
    print("=" * 80)
else:
    print("[-] MT5 Init failed.")