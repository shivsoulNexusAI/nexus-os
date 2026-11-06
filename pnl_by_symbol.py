import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe", portable=True):
    print("[-] MT5 Init Failed:", mt5.last_error())
    exit()

mt5.login(login=278025377, server="Exness-MT5Trial5")

now_utc = datetime.now(timezone.utc)
from_utc = now_utc - timedelta(hours=6)
deals = [d for d in (mt5.history_deals_get(from_utc, now_utc) or []) if d.entry == 1]

sym_pnl = {}
sym_counts = {}

for d in deals:
    sym_pnl[d.symbol] = sym_pnl.get(d.symbol, 0.0) + d.profit
    sym_counts[d.symbol] = sym_counts.get(d.symbol, 0) + 1

print("=" * 48)
print("       QUANT NEXUS: 6H REALIZED PnL BY ASSET    ")
print("=" * 48)
print(f"{'Symbol':<10} | {'Deals':<6} | {'Net Realized PnL':>16}")
print("-" * 48)

for s in sorted(sym_pnl.keys()):
    print(f"{s:<10} | {sym_counts[s]:<6} | ${sym_pnl[s]:>+15,.2f}")

print("-" * 48)
total_pnl = sum(sym_pnl.values())
print(f"{'TOTAL':<10} | {len(deals):<6} | ${total_pnl:>+15,.2f}")
print("=" * 48)

mt5.shutdown()
