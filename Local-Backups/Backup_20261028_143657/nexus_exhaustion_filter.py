"""
NEXUS EXHAUSTION FILTER // MEAN-REVERSION STRETCH & CLIMAX VETO ENGINE
"""
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

MAX_ATR_STRETCH = 2.25  # Max acceptable price distance from EMA21 in ATR units

def evaluate_exhaustion_gate(symbol: str, direction: str):
    """
    Evaluates whether price is over-extended relative to dynamic value baseline.
    Returns: (passed: bool, reason: str, metrics: dict)
    """
    if not mt5.initialize():
        return False, "MT5 disconnected", {}

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 45)
    if rates is None or len(rates) < 30:
        return True, "Insufficient bar history, bypassing filter", {}

    df = pd.DataFrame(rates)
    closes = df['close'].to_numpy()
    highs = df['high'].to_numpy()
    lows = df['low'].to_numpy()

    # Calculate 21 EMA baseline
    ema21 = float(pd.Series(closes).ewm(span=21).mean().iloc[-1])

    # Calculate 14 ATR
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
    atr14 = float(np.mean(tr[-14:]))
    if atr14 <= 0:
        return True, "Zero ATR, bypassing filter", {}

    current_price = closes[-1]
    stretch_distance = abs(current_price - ema21)
    stretch_ratio = stretch_distance / atr14

    # Determine if trade is in direction of existing over-extension
    is_buying_high = (direction.upper() == "BUY" and current_price > ema21)
    is_selling_low = (direction.upper() == "SELL" and current_price < ema21)

    metrics = {
        "price": round(current_price, 5),
        "ema21": round(ema21, 5),
        "atr14": round(atr14, 5),
        "stretch_ratio": round(stretch_ratio, 2),
        "max_stretch": MAX_ATR_STRETCH
    }

    if (is_buying_high or is_selling_low) and stretch_ratio > MAX_ATR_STRETCH:
        side_action = "BUYING top of climax" if is_buying_high else "SELLING bottom of drop"
        return False, f"Parabolic exhaustion: {side_action} (Stretched {stretch_ratio:.2f}x ATR > {MAX_ATR_STRETCH}x limit)", metrics

    return True, f"Price structure healthy (Stretch: {stretch_ratio:.2f}x ATR)", metrics
