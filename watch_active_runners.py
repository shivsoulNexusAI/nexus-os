import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if not mt5.initialize(path=TERMINAL, portable=False):
    exit(1)

acc = mt5.account_info()
positions = mt5.positions_get() or []

print("=" * 85)
print(f"ACCOUNT EQUITY SNAPSHOT | Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Floating: ${acc.profit:+,.2f}")
print("=" * 85)

for p in positions:
    side = "BUY" if p.type == 0 else "SELL"
    pts = (p.price_current - p.price_open) if side == "BUY" else (p.price_open - p.price_current)
    print(f"Runner #{p.ticket:<10} {p.symbol:<7} {side} {p.volume:.2f} lots | Entry: {p.price_open:.5f} | Mark: {p.price_current:.5f} | Move: {pts:>+8.2f} pts | PnL: ${p.profit:>+6.2f}")

print("=" * 85)
mt5.shutdown()