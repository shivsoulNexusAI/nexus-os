"""
NEXUS BIPOWER JUMP ENGINE // BARNDORFF-NIELSEN & SHEPHARD JUMP DECOMPOSITION
"""
import numpy as np
import MetaTrader5 as mt5

MAX_JUMP_RATIO = 0.35  # Veto if discontinuous jumps account for >= 35% of total variance
MU1_INV_SQ = np.pi / 2.0  # pi / 2 ≈ 1.570796

def calculate_bns_jump_ratio(closes: np.ndarray) -> tuple:
    """
    Computes Realized Variance (RV), Realized Bipower Variation (BV),
    and Relative Jump Ratio (J_rel) over trailing bars.
    """
    if len(closes) < 25:
        return 0.0, 0.0, 0.0

    returns = np.diff(np.log(np.maximum(closes, 1e-8)))
    n = len(returns)

    # 1. Realized Variance (RV)
    rv = float(np.sum(returns ** 2))
    if rv <= 1e-12:
        return 0.0, 0.0, 0.0

    # 2. Realized Bipower Variation (BV)
    abs_ret = np.abs(returns)
    bv = float(MU1_INV_SQ * np.sum(abs_ret[1:] * abs_ret[:-1]))

    # In finite samples, BV can slightly exceed RV due to microstructure noise
    bv = min(rv, bv)

    # 3. Relative Jump Proportion: J_rel = (RV - BV) / RV
    jump_var = max(0.0, rv - bv)
    j_rel = float(jump_var / rv)

    return round(rv, 8), round(bv, 8), round(j_rel, 3)

def evaluate_jump_gate(symbol: str, closes: np.ndarray):
    """
    Evaluates whether price variance is dominated by continuous drift vs discontinuous jump shocks.
    Returns: (passed: bool, reason: str, metrics: dict)
    """
    rv, bv, j_rel = calculate_bns_jump_ratio(closes)

    continuous_pct = round((1.0 - j_rel) * 100, 1)
    jump_pct = round(j_rel * 100, 1)

    metrics = {
        "symbol": symbol,
        "realized_variance": rv,
        "bipower_variation": bv,
        "jump_ratio": j_rel,
        "jump_pct": jump_pct,
        "continuous_pct": continuous_pct,
        "max_jump_ratio": MAX_JUMP_RATIO
    }

    if j_rel >= MAX_JUMP_RATIO:
        return False, f"Bipower Jump Shock Veto: Jumps account for {jump_pct}% of variance (>= {MAX_JUMP_RATIO*100:.0f}% limit). Transient liquidity shock.", metrics

    return True, f"Continuous Drift Validated: {continuous_pct}% continuous liquidity flow (Jump ratio: {j_rel:.2f})", metrics
