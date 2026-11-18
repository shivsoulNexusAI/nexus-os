# -*- coding: utf-8 -*-
"""
QUANT-NEXUS v10.10 PRODUCTION MONTE CARLO STRESS TEST (1,000 ITERATIONS)
Exact v10.10 parameters:
- T1 BTCUSD : 0.01L, 00:00-23:59 UTC, $4.50 max stop-risk cap
- T1 US30   : 0.01L, 07:00-20:59 UTC, uncapped ATR stop
- T2 GBPUSD : 0.02L, 07:00-20:59 UTC, M5 Sweep-Reclaim
- T3 XAUUSD : 0.01L, 07:00-20:59 UTC, full Hybrid Market + 15m TTL Stop
"""
import MetaTrader5 as mt5
import backtest_v10_8_2025_2026 as bt
import mc_v10_9_stress_test as mc9

SEED = 20261120

V1010_CONFIG = [
    {"sleeve": "T1", "base": "BTCUSD", "lot": 0.01, "max_spread_pts": 2500, "hr_start": 0, "hr_end": 23, "min_end": 59, "mode": "BREAKOUT",      "max_risk_usd": 4.50},
    {"sleeve": "T1", "base": "US30",   "lot": 0.01, "max_spread_pts": 450,  "hr_start": 7, "hr_end": 20, "min_end": 59, "mode": "BREAKOUT",      "max_risk_usd": 99.0},
    {"sleeve": "T2", "base": "GBPUSD", "lot": 0.02, "max_spread_pts": 18,   "hr_start": 7, "hr_end": 20, "min_end": 59, "mode": "SWEEP_RECLAIM", "max_risk_usd": 99.0},
    {"sleeve": "T3", "base": "XAUUSD", "lot": 0.01, "max_spread_pts": 280,  "hr_start": 7, "hr_end": 20, "min_end": 59, "mode": "HYBRID_GOLD",   "max_risk_usd": 99.0},
]

def main():
    print("=====================================================================================================")
    print(" QUANT-NEXUS v10.10 EXACT PRODUCTION MONTE CARLO STRESS TEST (1,000 Bootstrap Resamples)")
    print("=====================================================================================================")

    t1 = bt.SLEEVES[0]
    t2 = bt.SLEEVES[1]
    data_cache = {}

    mt5.initialize(path=t1["path"], login=t1["login"], password=t1["password"], server=t1["server"], portable=False)
    for b in ("BTCUSD", "US30", "XAUUSD"):
        sym, info, rates = bt.resolve_and_fetch(b, bt.START_UTC, bt.END_UTC)
        if sym and len(rates) >= 200:
            data_cache[b] = (sym, info, rates)
    mt5.shutdown()

    mt5.initialize(path=t2["path"], login=t2["login"], password=t2["password"], server=t2["server"], portable=False)
    sym, info, rates = bt.resolve_and_fetch("GBPUSD", bt.START_UTC, bt.END_UTC)
    if sym and len(rates) >= 200:
        data_cache["GBPUSD"] = (sym, info, rates)
    mt5.shutdown()

    print("\n--- 1. PER-SYMBOL v10.10 MONTE CARLO ($1,000 Starting Capital per Symbol) ---")
    all_trades = []
    for idx, cfg in enumerate(V1010_CONFIG):
        b = cfg["base"]
        if b not in data_cache:
            continue
        sym, info, rates = data_cache[b]
        t_list = mc9.extract_v109_trades(sym, info, rates, cfg)
        all_trades.extend(t_list)
        mc = mc9.run_mc(t_list, 1000.0, SEED + idx)
        print(
            f"  • {b:<8} ({mc['n']:>4}T) | MedDD: {mc['med_dd']:>5.2f}% | "
            f"95%ile DD: {mc['p95_dd']:>5.2f}% | 99%ile DD: {mc['p99_dd']:>5.2f}% | "
            f"MedNet: ${mc['med_net']:>+7.2f} | 5%ile Net: ${mc['p05_net']:>+7.2f} | "
            f"P(Profit): {mc['prob']:>5.1f}%"
        )

    if all_trades:
        fmc = mc9.run_mc(all_trades, 3000.0, SEED + 88)
        print("\n--- 2. COMBINED v10.10 3-TERMINAL FLEET MONTE CARLO ($3,000 Combined Capital) ---")
        print(f"  • Total Trades Resampled : {fmc['n']} trades")
        print(f"  • Median Max Drawdown    : {fmc['med_dd']:.2f}% (${3000.0 * fmc['med_dd'] / 100.0:.2f})")
        print(f"  • 95th-Percentile Max DD : {fmc['p95_dd']:.2f}% (${3000.0 * fmc['p95_dd'] / 100.0:.2f})")
        print(f"  • 99th-Percentile Max DD : {fmc['p99_dd']:.2f}% (${3000.0 * fmc['p99_dd'] / 100.0:.2f})")
        print(f"  • Median Net PnL         : ${fmc['med_net']:+.2f} (5th %ile: ${fmc['p05_net']:+.2f} | 95th %ile: ${fmc['p95_net']:+.2f})")
        print(f"  • Probability of Profit  : {fmc['prob']:.1f}%")
    print("=====================================================================================================")

if __name__ == "__main__":
    main()
