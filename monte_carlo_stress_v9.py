import csv
from pathlib import Path
import numpy as np

CSV_PATH = Path(r"C:\Quant-Nexus-Eng\reports\backtest_v9_2025_2026.csv")
START_CAPITAL = 11514.66  # Starting forward equity from v9.0 backtest final result
SIMULATIONS = 10000
TRADE_HORIZON = 500       # Simulate next 500 forward trades

def run_monte_carlo_v9() -> None:
    if not CSV_PATH.exists():
        print(f"[ERR] Audit CSV not found at {CSV_PATH}. Run backtest_v9_engine.py first.")
        return

    with CSV_PATH.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    pnl_samples = [float(r["net_pnl"]) for r in rows]
    if not pnl_samples:
        print("[ERR] No trades found in v9.0 audit CSV.")
        return

    print(f"=== SHIVSOUL NEXUS v9.0 // MONTE CARLO STRESS TEST ===")
    print(f"Historical Sample Size : {len(pnl_samples)} trades (2025-2026)")
    print(f"Starting Fleet Capital : ${START_CAPITAL:,.2f}")
    print(f"Monte Carlo Paths      : {SIMULATIONS:,}")
    print(f"Forward Horizon        : {TRADE_HORIZON} trades\n")

    pnl_array = np.array(pnl_samples)
    final_equities = np.zeros(SIMULATIONS)
    max_drawdowns = np.zeros(SIMULATIONS)

    np.random.seed(888)  # Reproducible random seed

    for i in range(SIMULATIONS):
        path_pnls = np.random.choice(pnl_array, size=TRADE_HORIZON, replace=True)
        equity_curve = START_CAPITAL + np.cumsum(path_pnls)
        
        running_max = np.maximum.accumulate(equity_curve)
        running_max = np.where(running_max <= 0, 1.0, running_max)
        drawdowns = (equity_curve - running_max) / running_max * 100.0

        final_equities[i] = equity_curve[-1]
        max_drawdowns[i] = abs(np.min(drawdowns))

    mean_eq = np.mean(final_equities)
    median_eq = np.median(final_equities)
    p5_eq = np.percentile(final_equities, 5)   # 95% Worst Case
    p95_eq = np.percentile(final_equities, 95) # 95% Best Case

    mean_dd = np.mean(max_drawdowns)
    p95_dd = np.percentile(max_drawdowns, 95)
    p99_dd = np.percentile(max_drawdowns, 99)
    ruin_prob = np.sum(final_equities <= 0) / SIMULATIONS * 100.0

    print(f"--- FORWARD EQUITY PROJECTIONS ({TRADE_HORIZON} TRADES) ---")
    print(f"  • Expected Final Equity (Mean)   : ${mean_eq:,.2f} ({((mean_eq-START_CAPITAL)/START_CAPITAL)*100:+.1f}%)")
    print(f"  • Median Final Equity            : ${median_eq:,.2f} ({((median_eq-START_CAPITAL)/START_CAPITAL)*100:+.1f}%)")
    print(f"  • 95% Best-Case Path (P95)       : ${p95_eq:,.2f} ({((p95_eq-START_CAPITAL)/START_CAPITAL)*100:+.1f}%)")
    print(f"  • 95% Worst-Case Path (P5)       : ${p95_eq:,.2f} ({((p95_eq-START_CAPITAL)/START_CAPITAL)*100:+.1f}%)")

    print(f"\n--- DRAWDOWN & RISK ENVELOPES ---")
    print(f"  • Average Max Drawdown           : {mean_dd:.2f}%")
    print(f"  • 95% Confidence Max Drawdown    : {p95_dd:.2f}%")
    print(f"  • 99% Extreme Tail Drawdown (P99): {p99_dd:.2f}%")
    print(f"  • Probability of Ruin (Eq <= $0) : {ruin_prob:.4f}%")
    print(f"============================================================")

if __name__ == "__main__":
    run_monte_carlo_v9()
