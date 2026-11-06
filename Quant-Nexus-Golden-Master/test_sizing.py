import MetaTrader5 as mt5
from quantum_delta_daemon import kelly_allocator, get_atr

if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    print(f"MT5 Init Failed: {mt5.last_error()}")
    exit(1)

symbols = ["XAUUSD", "EURUSD", "USDJPY", "BTCUSD"]
print("=== DYNAMIC KELLY SIZING SIMULATION (EDGE = 0.82) ===")
for sym in symbols:
    atr = get_atr(sym)
    if atr <= 0.0:
        print(f"[{sym}] ATR unavailable (returned 0.0)")
        continue
    
    sl_dist = atr * 1.5
    tp_dist = atr * 3.0
    sizing = kelly_allocator.calculate_lot_size(
        symbol=sym,
        edge_score=0.82,
        sl_distance_points=sl_dist,
        tp_distance_points=tp_dist
    )
    print(f"[{sym}] ATR: {atr:.4f} | Sizing Payload: {sizing}")

mt5.shutdown()
