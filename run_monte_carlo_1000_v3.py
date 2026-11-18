import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.append(r"C:\Program Files\Python312\Lib\site-packages")
sys.path.append(r"C:\Quant-Nexus-Eng")

import joblib
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from backtest_v3_fusion_2025_2026 import (
    TERMINAL, MODEL_V3_PATH, SYMBOLS, FEATURE_COLS_V3,
    INITIAL_CAPITAL, fetch_m5_history, build_m15_v44_v3_frame, run_symbol_v44_v3
)

OUT_MC_JSON = r"C:\Quant-Nexus-Eng\monte_carlo_v3_v44_1000_cert.json"
N_SIMS = 1000
DD_CAP_PCT = 3.0

def simulate_mc_paths(pnls: np.ndarray, n_sims: int, initial_cap: float, block_size: int = 1, slippage_haircut: float = 0.0, seed: int = 2026):
    rng = np.random.default_rng(seed)
    n_trades = len(pnls)
    adjusted_pnls = np.where(pnls > 0, pnls * (1.0 - slippage_haircut), pnls * (1.0 + slippage_haircut))

    final_equities = np.zeros(n_sims)
    max_dds_pct = np.zeros(n_sims)
    profit_factors = np.zeros(n_sims)
    max_consec_losses = np.zeros(n_sims, dtype=int)
    dd_breaches = 0
    ruin_count = 0

    for s in range(n_sims):
        if block_size <= 1:
            sample = rng.choice(adjusted_pnls, size=n_trades, replace=True)
        else:
            n_blocks = int(np.ceil(n_trades / block_size))
            starts = rng.integers(0, max(1, n_trades - block_size + 1), size=n_blocks)
            sample = np.concatenate([adjusted_pnls[st:st + block_size] for st in starts])[:n_trades]

        eq_curve = initial_cap + np.cumsum(sample)
        peaks = np.maximum.accumulate(np.maximum(initial_cap, eq_curve))
        dd_pcts = ((peaks - eq_curve) / peaks) * 100.0

        max_dd = float(np.max(dd_pcts))
        final_eq = float(eq_curve[-1])

        wins = float(np.sum(sample[sample > 0]))
        losses = float(np.abs(np.sum(sample[sample < 0])))
        pf = (wins / losses) if losses > 0 else 99.0

        # Max consecutive losing streak
        is_loss = (sample < 0).astype(int)
        streak = max_streak = 0
        for v in is_loss:
            if v:
                streak += 1
                if streak > max_streak:
                    max_streak = streak
            else:
                streak = 0

        final_equities[s] = final_eq
        max_dds_pct[s] = max_dd
        profit_factors[s] = pf
        max_consec_losses[s] = max_streak

        if max_dd > DD_CAP_PCT:
            dd_breaches += 1
        if np.min(eq_curve) <= initial_cap * 0.80:
            ruin_count += 1

    return {
        "n_simulations": n_sims,
        "trades_per_path": int(n_trades),
        "prob_profitable_pct": round(float(np.mean(final_equities > initial_cap) * 100.0), 2),
        "prob_dd_under_3pct": round(float((1.0 - dd_breaches / n_sims) * 100.0), 2),
        "prob_ruin_pct": round(float((ruin_count / n_sims) * 100.0), 2),
        "final_equity_percentiles": {
            "p05_worst_case": round(float(np.percentile(final_equities, 5)), 2),
            "p25_conservative": round(float(np.percentile(final_equities, 25)), 2),
            "p50_median": round(float(np.percentile(final_equities, 50)), 2),
            "p75_favorable": round(float(np.percentile(final_equities, 75)), 2),
            "p95_best_case": round(float(np.percentile(final_equities, 95)), 2),
        },
        "max_drawdown_pct_percentiles": {
            "p50_median": round(float(np.percentile(max_dds_pct, 50)), 2),
            "p90_tail": round(float(np.percentile(max_dds_pct, 90)), 2),
            "p95_extreme_tail": round(float(np.percentile(max_dds_pct, 95)), 2),
            "p99_worst_1pct": round(float(np.percentile(max_dds_pct, 99)), 2),
        },
        "profit_factor_percentiles": {
            "p05_tail": round(float(np.percentile(profit_factors, 5)), 2),
            "p50_median": round(float(np.percentile(profit_factors, 50)), 2),
            "p95_upper": round(float(np.percentile(profit_factors, 95)), 2),
        },
        "max_consec_losses_p95": int(np.percentile(max_consec_losses, 95)),
    }

def main():
    t0 = time.time()
    if not mt5.initialize(path=TERMINAL):
        print(f"[FATAL] MT5 init failed: {mt5.last_error()}")
        sys.exit(1)

    bundle = joblib.load(MODEL_V3_PATH)
    clf = bundle["model"]

    all_trades = []
    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        df_m5 = fetch_m5_history(sym)
        if df_m5.empty or not info:
            continue
        df_m15 = build_m15_v44_v3_frame(df_m5, sym, info.point)
        probs = clf.predict_proba(df_m15[FEATURE_COLS_V3])[:, 1]
        _, sym_trades = run_symbol_v44_v3(sym, df_m15, info, probs, ml_gate=0.42)
        all_trades.extend(sym_trades)

    mt5.shutdown()

    # Chronological Max-4 Concurrent Bracket Portfolio Filter
    all_trades.sort(key=lambda x: x["entry_dt"])
    active_exits = []
    portfolio_trades = []
    for tr in all_trades:
        active_exits = [et for et in active_exits if et > tr["entry_dt"]]
        if len(active_exits) >= 4:
            continue
        active_exits.append(tr["dt"])
        portfolio_trades.append(tr)

    pnls = np.array([t["pnl"] for t in portfolio_trades], dtype=float)

    # Regime 1: Pure 1,000-Run Bootstrap Resampling
    std_mc = simulate_mc_paths(pnls, n_sims=N_SIMS, initial_cap=INITIAL_CAPITAL, block_size=1, slippage_haircut=0.0, seed=2026)

    # Regime 2: 1,000-Run Adversarial Stress Test (Block-Clustered k=4 + 25% Live Slippage/Edge Haircut)
    stress_mc = simulate_mc_paths(pnls, n_sims=N_SIMS, initial_cap=INITIAL_CAPITAL, block_size=4, slippage_haircut=0.25, seed=9999)

    verdict = "CERTIFIED_REAL_EDGE" if (
        std_mc["prob_profitable_pct"] >= 99.0
        and stress_mc["prob_profitable_pct"] >= 95.0
        and std_mc["max_drawdown_pct_percentiles"]["p95_extreme_tail"] <= 4.5
    ) else "NEEDS_CALIBRATION"

    report = {
        "certified_at": datetime.now(timezone.utc).isoformat(),
        "system_version": "V3.0_ML + V4.4_ICT_DELTA_FUSION",
        "verdict": verdict,
        "historical_trades": int(len(pnls)),
        "mean_trade_pnl_usd": round(float(np.mean(pnls)), 2),
        "std_trade_pnl_usd": round(float(np.std(pnls)), 2),
        "t_stat_edge": round(float(np.mean(pnls) / (np.std(pnls) / np.sqrt(len(pnls)))), 2),
        "standard_bootstrap_1000": std_mc,
        "adversarial_stress_1000": stress_mc,
        "elapsed_sec": round(time.time() - t0, 2),
    }
    Path(OUT_MC_JSON).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 96)
    print(f"  MONTE CARLO 1,000-RUN CERTIFICATION | VERDICT: {verdict} (t-stat: {report['t_stat_edge']})")
    print("=" * 96)
    print(f"  Empirical Trade Stats (N={len(pnls)}): Mean=${report['mean_trade_pnl_usd']:+.2f}/trade | Std=${report['std_trade_pnl_usd']:.2f}")
    print("-" * 96)
    print("  [1] STANDARD BOOTSTRAP (1,000 Paths x 373 Trades)")
    print(f"      Prob Profitable : {std_mc['prob_profitable_pct']}% | Prob MaxDD <= 3.0%: {std_mc['prob_dd_under_3pct']}% | Ruin: {std_mc['prob_ruin_pct']}%")
    eq1 = std_mc["final_equity_percentiles"]
    dd1 = std_mc["max_drawdown_pct_percentiles"]
    pf1 = std_mc["profit_factor_percentiles"]
    print(f"      Final Equity    : P5=${eq1['p05_worst_case']} | P50(Median)=${eq1['p50_median']} | P95=${eq1['p95_best_case']}")
    print(f"      Max Drawdown    : P50={dd1['p50_median']}% | P90={dd1['p90_tail']}% | P95={dd1['p95_extreme_tail']}% | P99={dd1['p99_worst_1pct']}%")
    print(f"      Profit Factor   : P5={pf1['p05_tail']} | P50={pf1['p50_median']} | P95={pf1['p95_upper']} | P95 Max Losing Streak: {std_mc['max_consec_losses_p95']}")
    print("-" * 96)
    print("  [2] ADVERSARIAL STRESS TEST (1,000 Paths | Block=4 Clustering + 25% Slippage/Edge Haircut)")
    print(f"      Prob Profitable : {stress_mc['prob_profitable_pct']}% | Prob MaxDD <= 3.0%: {stress_mc['prob_dd_under_3pct']}% | Ruin: {stress_mc['prob_ruin_pct']}%")
    eq2 = stress_mc["final_equity_percentiles"]
    dd2 = stress_mc["max_drawdown_pct_percentiles"]
    pf2 = stress_mc["profit_factor_percentiles"]
    print(f"      Final Equity    : P5=${eq2['p05_worst_case']} | P50(Median)=${eq2['p50_median']} | P95=${eq2['p95_best_case']}")
    print(f"      Max Drawdown    : P50={dd2['p50_median']}% | P90={dd2['p90_tail']}% | P95={dd2['p95_extreme_tail']}% | P99={dd2['p99_worst_1pct']}%")
    print(f"      Profit Factor   : P5={pf2['p05_tail']} | P50={pf2['p50_median']} | P95={pf2['p95_upper']} | P95 Max Losing Streak: {stress_mc['max_consec_losses_p95']}")
    print("-" * 96)
    print(f"  Saved report -> {OUT_MC_JSON} (Completed in {report['elapsed_sec']}s)")
    print("=" * 96)

if __name__ == "__main__":
    main()
