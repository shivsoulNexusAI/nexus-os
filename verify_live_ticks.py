import MetaTrader5 as mt5
import sys
from datetime import datetime

T2_PATH = r"C:\MT5_Pending_278041169\terminal64.exe"
SYMBOLS = ["US30", "GBPUSD", "XAUUSD", "BTCUSD", "EURUSD"]

print("==========================================================")
print(" LIVE TICK-LEVEL TERMINAL 2 VERIFICATION HARMESS")
print("==========================================================")

if not mt5.initialize(path=T2_PATH, portable=True, timeout=10000):
    print(f"[CRITICAL ERROR] Terminal 2 initialization failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
print(f"[OK] Connected to Terminal 2 | Account: {ai.login} | Server: {ai.server}")
print(f"     Balance: ${ai.balance:,.2f} | Equity: ${ai.equity:,.2f}")

print("\n--- REAL-TIME TICK & SPREAD INSPECTION ---")
for sym in SYMBOLS:
    if not mt5.symbol_select(sym, True):
        print(f"  [WARNING] Symbol {sym} could not be selected.")
        continue
    
    tick = mt5.symbol_info_tick(sym)
    info = mt5.symbol_info(sym)
    if tick and info:
        spread = round((tick.ask - tick.bid) / info.point, 1)
        print(f"  {sym:<8} | Bid: {tick.bid:<10} | Ask: {tick.ask:<10} | Spread: {spread:>5} pts | Digits: {info.digits}")
    else:
        print(f"  {sym:<8} | Tick stream unavailable.")

print("\n--- ACTIVE POSITIONS & ORDERS AUDIT ---")
positions = mt5.positions_get() or []
orders = mt5.orders_get() or []
print(f"  Active Positions : {len(positions)}")
print(f"  Pending OCO Orders : {len(orders)}")

if orders:
    for o in orders:
        print(f"    -> Order #{o.ticket} | {o.symbol} | Type: {o.type} | Price: {o.price_open} | SL: {o.sl}")

mt5.shutdown()
print("==========================================================")
print("[SUCCESS] Live tick-level verification completed successfully.")
print("==========================================================")
