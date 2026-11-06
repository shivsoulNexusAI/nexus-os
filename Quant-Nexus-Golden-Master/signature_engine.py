"""
Quant Nexus Microstructure & Signature Engine
Enhanced with ICT Institutional Microstructure Models (MMSM / MMBM)
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd


def detect_candlestick_pattern(df: pd.DataFrame) -> str:
    """Classifies primary 2-bar candlestick formations."""
    if len(df) < 2:
        return "INSUFFICIENT_DATA"
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    is_prev_bear = prev['close'] < prev['open']
    is_curr_bull = curr['close'] > curr['open']
    is_prev_bull = prev['close'] > prev['open']
    is_curr_bear = curr['close'] < curr['open']

    if is_prev_bear and is_curr_bull and curr['close'] > prev['open'] and curr['open'] < prev['close']:
        return "BULLISH_ENGULFING"
    if is_prev_bull and is_curr_bear and curr['close'] < prev['open'] and curr['open'] > prev['close']:
        return "BEARISH_ENGULFING"
    return "NEUTRAL_STRUCTURE"


def detect_fair_value_gap(df: pd.DataFrame, min_gap_points: float = 0.0) -> str:
    """
    Evaluates a 3-bar window for Imbalance / Fair Value Gap (FVG).
    Maintained for strict backward-compatibility with matrix tokenizers.
    """
    if len(df) < 4:
        return "NO_FVG"
    c1 = df.iloc[-4]
    c3 = df.iloc[-2]

    # Bullish FVG: Low of candle 3 is higher than High of candle 1
    if c3['low'] > c1['high'] + min_gap_points:
        return "FVG"

    # Bearish FVG: High of candle 3 is lower than Low of candle 1
    if c3['high'] < c1['low'] - min_gap_points:
        return "FVG"

    return "NO_FVG"


def extract_ict_microstructure(
    df: pd.DataFrame, 
    atr_period: int = 14,
    lookback_bars: int = 40
) -> Dict[str, Any]:
    """
    Vectorized institutional calculation of ICT Market Maker Sell Model (MMSM)
    and Market Maker Buy Model (MMBM).
    
    Returns:
        - Equilibrium 50% boundary (Premium vs Discount threshold)
        - Exact FVG boundaries (Floor, Ceiling, Consequent Encroachment)
        - Liquidity sweep flag (BSL / SSL raid)
        - Executable institutional trade parameters
    """
    if len(df) < lookback_bars:
        return {"valid": False, "reason": "Insufficient historical depth"}

    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values

    # 1. Volatility Baseline (True Range & ATR)
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1]))
    )
    atr = float(np.mean(tr[-atr_period:])) if len(tr) >= atr_period else 1.0

    # 2. Structural Anchor Points
    window_highs = highs[-lookback_bars:]
    window_lows = lows[-lookback_bars:]
    
    swing_high_idx = int(np.argmax(window_highs[:-5]))
    swing_high = float(window_highs[swing_high_idx])
    
    swing_low_idx = int(np.argmin(window_lows[swing_high_idx:])) + swing_high_idx
    swing_low = float(window_lows[swing_low_idx])
    
    equilibrium_50 = (swing_high + swing_low) / 2.0
    current_price = float(closes[-1])

    # 3. Buy-Side Liquidity (BSL) Sweep Detection
    # Price pierced above the swing high on wicks but failed to close above
    bsl_swept = False
    for i in range(len(highs) - 15, len(highs)):
        if highs[i] > swing_high and closes[i] <= swing_high:
            bsl_swept = True
            break

    # 4. Fair Value Gap (FVG) Scan (Multi-bar memory)
    bearish_fvg = None
    bullish_fvg = None

    for i in range(len(df) - 1, max(len(df) - 12, 2), -1):
        c1_low = float(lows[i - 2])
        c1_high = float(highs[i - 2])
        c3_high = float(highs[i])
        c3_low = float(lows[i])

        # Bearish Imbalance: Candle 3 High is lower than Candle 1 Low
        if c1_low > c3_high and (c1_low - c3_high) >= (0.20 * atr):
            gap_floor = c3_high
            gap_ceiling = c1_low
            consequent_encroachment = (gap_floor + gap_ceiling) / 2.0
            
            # Check if gap is already fully mitigated
            mitigated = any(highs[j] >= gap_ceiling for j in range(i + 1, len(df)))
            if not mitigated:
                bearish_fvg = {
                    "type": "BEARISH_FVG",
                    "floor": round(gap_floor, 2),
                    "ceiling": round(gap_ceiling, 2),
                    "ce_50": round(consequent_encroachment, 2),
                    "bar_index": i - 1
                }
                break

        # Bullish Imbalance: Candle 3 Low is higher than Candle 1 High
        if c3_low > c1_high and (c3_low - c1_high) >= (0.20 * atr):
            gap_floor = c1_high
            gap_ceiling = c3_low
            consequent_encroachment = (gap_floor + gap_ceiling) / 2.0
            
            mitigated = any(lows[j] <= gap_floor for j in range(i + 1, len(df)))
            if not mitigated:
                bullish_fvg = {
                    "type": "BULLISH_FVG",
                    "floor": round(gap_floor, 2),
                    "ceiling": round(gap_ceiling, 2),
                    "ce_50": round(consequent_encroachment, 2),
                    "bar_index": i - 1
                }
                break

    # 5. ICT MMSM Institutional Setup Qualification
    is_mmsm_setup = False
    trade_plan = None

    if bsl_swept and bearish_fvg is not None:
        # Check if price is pulling back towards or into the FVG zone
        in_or_near_fvg = current_price >= (bearish_fvg['floor'] - (0.5 * atr))
        if in_or_near_fvg:
            is_mmsm_setup = True
            entry_price = bearish_fvg['ceiling']
            stop_loss = round(bearish_fvg['ceiling'] + (0.75 * atr), 2)
            tp1_halfway = round(equilibrium_50, 2)
            tp2_ssl = round(swing_low, 2)
            
            risk_points = max(stop_loss - entry_price, 0.1)
            reward_points = entry_price - tp2_ssl
            rr_ratio = round(reward_points / risk_points, 2)

            trade_plan = {
                "model": "ICT_BEARISH_MMSM",
                "bias": "SHORT",
                "entry_limit": entry_price,
                "entry_zone": (bearish_fvg['floor'], bearish_fvg['ceiling']),
                "consequent_encroachment": bearish_fvg['ce_50'],
                "stop_loss": stop_loss,
                "take_profit_1": tp1_halfway,
                "take_profit_2_ssl": tp2_ssl,
                "projected_rr": rr_ratio,
                "atr": round(atr, 2)
            }

    return {
        "valid": True,
        "current_price": round(current_price, 2),
        "swing_high_bsl": round(swing_high, 2),
        "swing_low_ssl": round(swing_low, 2),
        "equilibrium_50": round(equilibrium_50, 2),
        "zone_classification": "PREMIUM" if current_price >= equilibrium_50 else "DISCOUNT",
        "bsl_swept": bsl_swept,
        "active_fvg": bearish_fvg or bullish_fvg,
        "mmsm_setup_active": is_mmsm_setup,
        "trade_plan": trade_plan
    }


def detect_vwap_relation(df: pd.DataFrame, threshold_percent: float = 0.05) -> str:
    """Calculates Intraday Anchored VWAP and classifies position / retest."""
    if len(df) < 5 or "tick_volume" not in df.columns:
        return "VWAP_NEUTRAL"
    typical_price = (df['high'] + df['low'] + df['close']) / 3.0
    vol = df['tick_volume']
    cum_pv = (typical_price * vol).cumsum()
    cum_v = vol.cumsum()
    vwap = cum_pv / (cum_v + 1e-9)
    current_vwap = vwap.iloc[-1]
    current_close = df['close'].iloc[-1]
    pct_dist = ((current_close - current_vwap) / current_vwap) * 100.0

    if abs(pct_dist) <= threshold_percent:
        return "VWAP_RETEST"
    elif pct_dist > 0:
        return "VWAP_ABOVE"
    else:
        return "VWAP_BELOW"


def generate_market_signature(df: pd.DataFrame, timeframe_str: str = "M15") -> str:
    """Compiles multi-feature tokens into a deterministic signature."""
    tokens = [timeframe_str.upper()]
    candlestick = detect_candlestick_pattern(df)
    if candlestick != "NEUTRAL_STRUCTURE":
        tokens.append(candlestick)
    fvg = detect_fair_value_gap(df)
    if fvg != "NO_FVG":
        tokens.append(fvg)
    vwap = detect_vwap_relation(df)
    if vwap != "VWAP_NEUTRAL":
        tokens.append(vwap)
    return "+".join(tokens)
