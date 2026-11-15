import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    pos = mt5.positions_get(ticket=2827676341)
    if pos:
        p = pos[0]
        pts_profit = (p.price_open - p.price_current) / 0.00001
        print("=" * 80)
        print(f"POSITION AUDIT: Ticket #{p.ticket} ({p.symbol})")
        print(f"Entry: {p.price_open:.5f} | Current: {p.price_current:.5f} | Profit: +{pts_profit:.1f} pts (${p.profit:.2f})")
        print(f"Current SL: {p.sl:.5f} | Proposed BE: {p.price_open:.5f}")
        print("=" * 80)
    else:
        print("[-] Position #2827676341 not found.")
    mt5.shutdown()