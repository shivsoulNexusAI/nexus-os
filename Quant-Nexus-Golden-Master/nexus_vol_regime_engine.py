"""
NEXUS VOLATILITY REGIME ENGINE // PARKINSON EXTREME-VALUE DYNAMIC TARGET MODULATION
"""
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

def calculate_parkinson_volatility(highs: np.ndarray, lows: np.ndarray, period: int = 14) -> float:
    """Calculates Parkinson extreme-value volatility estimator."""
    if len(highs) < period or len(lows) < period:
        return 0.001
    
    h = highs[-period:]
    l = lows[-period:]
    # Avoid zero division or log(0)
    ratio = np.maximum(h / np.maximum(l, 1e-8), 1.000001)
    log_hl = np.log(ratio)
    sum_sq = np.sum(log_hl ** 2)
    vol = np.sqrt((1.0 / (4.0 * np.log(2.0) * period)) * sum_sq)
    return float(vol)

def evaluate_volatility_regime(symbol: str):
    """
    Evaluates short-term vs long-term Parkinson volatility ratio.
    Returns: (regime_name: str, phi_ratio: float, sl_mult: float, tp1_mult: float, size_scalar: float)
    """
    if not mt5.initialize():
        return "BASELINE", 1.0, 1.5, 1.2, 1.0

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)
    if rates is None or len(rates) < 45:
        return "BASELINE", 1.0, 1.5, 1.2, 1.0

    df = pd.DataFrame(rates)
    highs = df['high'].to_numpy()
    lows = df['low'].to_numpy()

    # Short (10 bars) vs Long (40 bars) Parkinson Volatility
    vol_short = calculate_parkinson_volatility(highs, lows, period=10)
    vol_long = calculate_parkinson_volatility(highs, lows, period=40)

    phi = vol_short / vol_long if vol_long > 0 else 1.0
    phi = round(float(np.clip(phi, 0.40, 2.50)), 2)

    if phi < 0.80:
        regime = "COMPRESSION"
        sl_mult = 1.20
        tp1_mult = 1.60
        size_scalar = 1.0
    elif phi > 1.35:
        regime = "VOL_SHOCK"
        sl_mult = min(2.00, round(1.50 * np.sqrt(phi), 2))
        tp1_mult = 1.00
        size_scalar = round(min(1.0, 1.0 / phi), 2)
    else:
        regime = "STEADY_TREND"
        sl_mult = 1.50
        tp1_mult = 1.20
        size_scalar = 1.0

    return regime, phi, sl_mult, tp1_mult, size_scalar
