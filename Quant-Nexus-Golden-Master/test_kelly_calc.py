import MetaTrader5 as mt5
from nexus_kelly_engine import kelly_engine

if not mt5.initialize():
    print("[!] MT5 initialization failed.")
    exit(1)

equity = 1380.0

tests = [
    ("BTCUSD", 77.0, 75900.0, 76200.0, 75300.0, 0.08),
    ("USDJPY", 78.0, 157.80, 157.65, 158.10, 0.05),
    ("XAUUSD", 82.0, 4100.0, 4108.0, 4084.0, 0.03),
    ("GBPUSD", 76.0, 1.3450, 1.3470, 1.3410, 0.04)
]

print("=" * 65)
print(f"{'SYMBOL':<8} {'EDGE':<8} {'PAYOFF (b)':<12} {'KELLY LOT':<12} {'HARD CAP':<10}")
print("=" * 65)

for sym, prob, entry, sl, tp, cap in tests:
    sl_dist = abs(entry - sl)
    tp_dist = abs(entry - tp)
    b_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 1.0
    lot = kelly_engine.compute_position_size(sym, prob, entry, sl, tp, equity, cap)
    print(f"{sym:<8} {prob}%{'':<3} {b_ratio:<12} {lot:<12} {cap:<10}")

print("=" * 65)
mt5.shutdown()
