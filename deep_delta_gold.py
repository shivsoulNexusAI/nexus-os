import MetaTrader5 as mt5
from pathlib import Path

TERMINAL = r"C:/MT5_HFT_278041671/terminal64.exe"

print("=" * 85)
print("PART 1: TERMINAL 3 STOPS LEVEL & ACTIVE BRACKET SNAPSHOT")
print("=" * 85)
if mt5.initialize(path=TERMINAL, portable=False, timeout=10000):
    acc = mt5.account_info()
    sym_info = mt5.symbol_info("XAUUSD")
    tick = mt5.symbol_info_tick("XAUUSD")
    orders = mt5.orders_get(symbol="XAUUSD") or []
    
    print(f"Account: #{acc.login} | Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f}")
    print(f"Spot: Bid {tick.bid:.3f} | Ask {tick.ask:.3f} | Spread: ${(tick.ask - tick.bid):.3f}")
    print(f"Trade Stops Level : {sym_info.trade_stops_level} points (Min distance required: ${sym_info.trade_stops_level * sym_info.point:.3f})")
    print(f"Active XAUUSD Orders: {len(orders)}")
    for o in orders:
        ot = "BUY_STOP" if o.type == 4 else ("SELL_STOP" if o.type == 5 else str(o.type))
        print(f"  -> #{o.ticket} {ot} {o.volume_current:.2f}L @ {o.price_open:.3f} | SL: {o.sl:.3f} | TP: {o.tp:.3f} | Magic: {o.magic}")
    mt5.shutdown()
else:
    print(f"[-] Terminal 3 init failed: {mt5.last_error()}")

print("\n" + "=" * 85)
print("PART 2: LINES 194-255 OF gold_hft_straddle_daemon.py")
print("=" * 85)
lines = Path(r"C:\Quant-Nexus-Eng\gold_hft_straddle_daemon.py").read_text(encoding="utf-8", errors="ignore").splitlines()
for i in range(193, min(len(lines), 260)):
    print(f"{i+1:4d}: {lines[i]}")
print("=" * 85)