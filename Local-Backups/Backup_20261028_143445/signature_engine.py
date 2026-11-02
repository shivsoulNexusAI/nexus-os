import numpy as np
import pandas as pd
import MetaTrader5 as mt5

def detect_candlestick_pattern(df: pd.DataFrame) -> str:
    """
    Evaluates the last two completed bars for Engulfing patterns.
    Index -1: Active/forming bar
    Index -2: Last completed trigger candle
    Index -3: Preceding setup candle
    """
    curr = df.iloc[-2]
    prev = df.iloc[-3]

    curr_body = abs(curr['close'] - curr['open'])
    prev_body = abs(prev['close'] - prev['open'])

    # Bullish Engulfing: previous bearish, current bullish, closes above previous open
    if prev['close'] < prev['open'] and curr['close'] > curr['open']:
        if curr['close'] >= prev['open'] and curr['open'] <= prev['close'] and curr_body > prev_body:
            return "BULLISH_ENGULFING"

    # Bearish Engulfing: previous bullish, current bearish, closes below previous open
    if prev['close'] > prev['open'] and curr['close'] < curr['open']:
        if curr['close'] <= prev['open'] and curr['open'] >= prev['close'] and curr_body > prev_body:
            return "BEARISH_ENGULFING"

    # Default directional momentum
    return "MOMENTUM_EXPANSION" if curr['close'] > curr['open'] else "MOMENTUM_CONTRACTION"

def detect_fair_value_gap(df: pd.DataFrame, min_gap_points: float = 0.0) -> str:
    """
    Evaluates a 3-bar window for Imbalance / Fair Value Gap (FVG).
    Bar -4 (Candle 1), Bar -3 (Candle 2 / Impulse), Bar -2 (Candle 3)
    """
    c1 = df.iloc[-4]
    c3 = df.iloc[-2]

    # Bullish FVG: Low of candle 3 is higher than High of candle 1
    if c3['low'] > c1['high'] + min_gap_points:
        return "FVG"

    # Bearish FVG: High of candle 3 is lower than Low of candle 1
    if c3['high'] < c1['low'] - min_gap_points:
        return "FVG"

    return "NO_FVG"

def detect_vwap_relation(df: pd.DataFrame, threshold_percent: float = 0.05) -> str:
    """
    Calculates Intraday Anchored VWAP and classifies position / retest.
    VWAP = cumsum(Typical Price * Volume) / cumsum(Volume)
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3.0
    vol = df['tick_volume']
    
    # Intraday cumulative anchor (last 48 bars on M15 = ~12 hours)
    anchor_slice = slice(-48, None)
    cum_pv = (typical_price[anchor_slice] * vol[anchor_slice]).cumsum()
    cum_vol = vol[anchor_slice].cumsum()
    
    vwap_series = cum_pv / cum_vol
    current_close = df['close'].iloc[-2]
    current_vwap = vwap_series.iloc[-1]

    pct_diff = abs(current_close - current_vwap) / current_vwap * 100.0

    if pct_diff <= threshold_percent:
        return "VWAP_RETEST"
    elif current_close > current_vwap:
        return "ABOVE_VWAP"
    else:
        return "BELOW_VWAP"

def build_confluence_signature(symbol: str, timeframe_str: str = "M15") -> str:
    """
    Pulls recent bars directly from MT5 and builds the standardized signature string.
    Example output: 'M15_BULLISH_ENGULFING+FVG+VWAP_RETEST'
    """
    tf_map = {
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4
    }
    tf = tf_map.get(timeframe_str, mt5.TIMEFRAME_M15)

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, 60)
    if rates is None or len(rates) < 10:
        return f"{timeframe_str}_BASE_PRICE_ACTION"

    df = pd.DataFrame(rates)

    # 1. Classify Price Structure
    pattern = detect_candlestick_pattern(df)
    
    # 2. Classify Liquidity Imbalance
    fvg = detect_fair_value_gap(df)

    # 3. Classify Session Baseline
    vwap = detect_vwap_relation(df)

    # 4. Assemble tokens into standardized signature
    tokens = [f"{timeframe_str}_{pattern}"]
    if fvg != "NO_FVG":
        tokens.append(fvg)
    tokens.append(vwap)

    return "+".join(tokens)