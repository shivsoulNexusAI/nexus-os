import MetaTrader5 as mt5
import backtest_v10_8_2025_2026 as bt
import mc_v10_9_stress_test as mc9

SEED = 20261121
V1011_CONFIG = [
    {"sleeve": "T1", "base": "BTCUSD", "lot": 0.01, "max_spread_pts": 2500, "hr_start": 0, "hr_end": 23, "min_end": 59, "mode": "BREAKOUT",      "max_risk_usd": 4.50},
    {"sleeve": "T1", "base": "US30",   "lot": 0.01, "max_spread_pts": 450,  "hr_start": 7, "hr_end": 20, "min_end": 59, "mode": "BREAKOUT",      "max_risk_usd": 99.0},
    {"sleeve": "T2", "base": "GBPUSD", "lot": 0.02, "max_spread_pts": 18,   "hr_start": 7, "hr_end": 20, "min_end": 59, "mode": "SWEEP_RECLAIM", "max_risk_usd": 99.0},
    {"sleeve": "T3", "base": "XAUUSD", "lot": 0.01, "max_spread_pts": 280,  "hr_start": 7, "hr_end": 20, "min_end": 59, "mode": "HYBRID_GOLD",   "max_risk_usd": 9.50},
]

def main():
    t1, t2 = bt.SLEEVES[0], bt.SLEEVES[1]
    cache = {}
    mt5.initialize(path=t1["path"], login=t1["login"], password=t1["password"], server=t1["server"], portable=False)
    for b in ("BTCUSD", "US30", "XAUUSD"):
        sym, info, rates = bt.resolve_and_fetch(b, bt.START_UTC, bt.END_UTC)
        if sym and len(rates) >= 200:
            cache[b] = (sym, info, rates)
    mt5.shutdown()

    mt5.initialize(path=t2["path"], login=t2["login"], password=t2["password"], server=t2["server"], portable=False)
    sym, info, rates = bt.resolve_and_fetch("GBPUSD", bt.START_UTC, bt.END_UTC)
    if sym and len(rates) >= 200:
        cache["GBPUSD"] = (sym, info, rates)
    mt5.shutdown()

    all_trades = []
    for idx, cfg in enumerate(V1011_CONFIG):
        b = cfg["base"]
        t_list = mc9.extract_v109_trades(*cache[b], cfg)
        all_trades.extend(t_list)
        mc = mc9.run_mc(t_list, 1000.0, SEED + idx)
        print(f"  • {b:<8} ({mc['n']:>4}T) | MedDD: {mc['med_dd']:>5.2f}% | 95%ile DD: {mc['p95_dd']:>5.2f}% | MedNet: ${mc['med_net']:>+7.2f} | P(Profit): {mc['prob']:>5.1f}%")

    fmc = mc9.run_mc(all_trades, 3000.0, SEED + 88)
    print(f"\n  [FLEET $3k] MedDD: {fmc['med_dd']:.2f}% | 95%ile DD: {fmc['p95_dd']:.2f}% | MedNet: ${fmc['med_net']:+.2f} | P(Profit): {fmc['prob']:.1f}%")

if __name__ == "__main__":
    main()
