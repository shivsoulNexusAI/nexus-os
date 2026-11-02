"""
NEXUS FRACTAL PERSISTENCE ENGINE // HURST EXPONENT & RANDOM-WALK NOISE SHIELD
"""
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

MIN_PERSISTENT_HURST = 0.55  # Minimum Hurst required to confirm true trend memory

def calculate_hurst_rs(prices: np.ndarray) -> float:
    """
    Computes empirical Hurst exponent using Rescaled Range (R/S) analysis over dyadic windows.
    """
    if len(prices) < 60:
        return 0.50

    # Calculate log returns
    returns = np.diff(np.log(np.maximum(prices, 1e-8)))
    n = len(returns)

    # Sub-window scales (tau)
    lags = [16, 32, 64]
    lags = [lag for lag in lags if lag <= n]
    if len(lags) < 2:
        return 0.50

    rs_values = []

    for lag in lags:
        num_chunks = n // lag
        rs_chunk_list = []
        for i in range(num_chunks):
            chunk = returns[i * lag : (i + 1) * lag]
            mean_val = np.mean(chunk)
            deviates = np.cumsum(chunk - mean_val)
            r = np.max(deviates) - np.min(deviates)
            s = np.std(chunk, ddof=1)
            if s > 1e-8:
                rs_chunk_list.append(r / s)
        if rs_chunk_list:
            rs_values.append(np.mean(rs_chunk_list))

    if len(rs_values) < 2:
        return 0.50

    # Linear regression in log-log space: ln(R/S) = H * ln(lag) + c
    log_lags = np.log(lags[:len(rs_values)])
    log_rs = np.log(rs_values)

    poly = np.polyfit(log_lags, log_rs, 1)
    hurst = float(np.clip(poly[0], 0.10, 0.95))
    return round(hurst, 3)

def evaluate_fractal_gate(symbol: str):
    """
    Evaluates whether the asset is in a persistent trending state vs random-walk noise.
    Returns: (passed: bool, hurst_val: float, regime: str, metrics: dict)
    """
    if not mt5.initialize():
        return True, 0.55, "MT5_BYPASS", {}

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 75)
    if rates is None or len(rates) < 65:
        return True, 0.55, "INSUFFICIENT_DATA", {}

    closes = np.array([r[4] for r in rates], dtype=np.float64)
    hurst = calculate_hurst_rs(closes)

    if hurst < 0.48:
        regime = "ANTI_PERSISTENT_CHOP"
    elif hurst < MIN_PERSISTENT_HURST:
        regime = "RANDOM_WALK_NOISE"
    else:
        regime = "PERSISTENT_TREND"

    metrics = {
        "symbol": symbol,
        "hurst_exponent": hurst,
        "regime": regime,
        "min_required": MIN_PERSISTENT_HURST
    }

    if hurst < MIN_PERSISTENT_HURST:
        return False, hurst, f"Fractal Noise Veto: Hurst {hurst:.3f} < {MIN_PERSISTENT_HURST} threshold ({regime})", metrics

    return True, hurst, f"Persistent Trend Validated: Hurst {hurst:.3f} ({regime})", metrics
