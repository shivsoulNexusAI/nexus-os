import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def find_swings(df: pd.DataFrame, window: int = 5):
    """Identifies swing highs and swing lows across a dataframe."""
    highs = []
    lows = []
    for i in range(window, len(df) - window):
        is_high = all(df['high'].iloc[i] > df['high'].iloc[i - j] and df['high'].iloc[i] > df['high'].iloc[i + j] for j in range(1, window + 1))
        is_low = all(df['low'].iloc[i] < df['low'].iloc[i - j] and df['low'].iloc[i] < df['low'].iloc[i + j] for j in range(1, window + 1))
        if is_high:
            highs.append((df.index[i], df['high'].iloc[i]))
        if is_low:
            lows.append((df.index[i], df['low'].iloc[i]))
    return highs, lows

def evaluate_smt_divergence(sym_a: str = "EURUSD", sym_b: str = "GBPUSD", timeframe=mt5.TIMEFRAME_M5) -> dict:
    """
    Evaluates SMT Divergence between two correlated assets (Default: EURUSD vs GBPUSD).
    Returns divergence type, edge multiplier, and descriptive reason.
    """
    rates_a = mt5.copy_rates_from_pos(sym_a, timeframe, 0, 100)
    rates_b = mt5.copy_rates_from_pos(sym_b, timeframe, 0, 100)

    if rates_a is None or rates_b is None or len(rates_a) < 30 or len(rates_b) < 30:
        return {"divergence": "NONE", "boost": 0, "reason": "Insufficient rate data"}

    df_a = pd.DataFrame(rates_a)
    df_b = pd.DataFrame(rates_b)

    highs_a, lows_a = find_swings(df_a, window=3)
    highs_b, lows_b = find_swings(df_b, window=3)

    if len(lows_a) < 2 or len(lows_b) < 2 or len(highs_a) < 2 or len(highs_b) < 2:
        return {"divergence": "NONE", "boost": 0, "reason": "Insufficient swing count"}

    # Bullish SMT: Compare last 2 swing lows
    # Low 1: prior, Low 2: recent
    a_l1, a_l2 = lows_a[-2][1], lows_a[-1][1]
    b_l1, b_l2 = lows_b[-2][1], lows_b[-1][1]

    # Asset A makes Lower Low while Asset B makes Higher Low
    if a_l2 < a_l1 and b_l2 >= b_l1:
        return {
            "divergence": "BULLISH_SMT",
            "leader": sym_b,
            "laggard_swept": sym_a,
            "boost": +15,
            "reason": f"Bullish SMT: {sym_a} swept Lower Low while {sym_b} preserved Higher Low"
        }
    elif b_l2 < b_l1 and a_l2 >= a_l1:
        return {
            "divergence": "BULLISH_SMT",
            "leader": sym_a,
            "laggard_swept": sym_b,
            "boost": +15,
            "reason": f"Bullish SMT: {sym_b} swept Lower Low while {sym_a} preserved Higher Low"
        }

    # Bearish SMT: Compare last 2 swing highs
    a_h1, a_h2 = highs_a[-2][1], highs_a[-1][1]
    b_h1, b_h2 = highs_b[-2][1], highs_b[-1][1]

    if a_h2 > a_h1 and b_h2 <= b_h1:
        return {
            "divergence": "BEARISH_SMT",
            "leader": sym_b,
            "laggard_swept": sym_a,
            "boost": +15,
            "reason": f"Bearish SMT: {sym_a} pushed Higher High while {sym_b} made Lower High"
        }
    elif b_h2 > b_h1 and a_h2 <= a_h1:
        return {
            "divergence": "BEARISH_SMT",
            "leader": sym_a,
            "laggard_swept": sym_b,
            "boost": +15,
            "reason": f"Bearish SMT: {sym_b} pushed Higher High while {sym_a} made Lower High"
        }

    return {"divergence": "NONE", "boost": 0, "reason": "Aligned Market Structure (No Divergence)"}

if __name__ == "__main__":
    if mt5.initialize():
        print("=" * 65)
        print("🔍 AUDITING INSTITUTIONAL SMT MATRIX (M5)")
        print("=" * 65)
        fx_smt = evaluate_smt_divergence("EURUSD", "GBPUSD")
        print(f"FX PAIR (EUR/GBP) : {fx_smt['divergence']} (+{fx_smt['boost']}%)")
        print(f"Details           : {fx_smt['reason']}")
        print("=" * 65)
        mt5.shutdown()
