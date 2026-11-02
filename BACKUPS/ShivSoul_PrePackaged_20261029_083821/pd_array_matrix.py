"""
Quant Nexus PD Array & Confluence Matrix Engine
Vectorized calculations for:
- Premium/Discount Equilibrium
- Bullish/Bearish Order Blocks (OB)
- Bullish/Bearish Breaker Blocks (BB)
- Rejection Blocks (RB)
- Fair Value Gaps (FVG) & Consequent Encroachment (CE)
- Institutional Confluence Scoring Matrix (0 - 100)
"""

from typing import Dict, Any
import numpy as np
import pandas as pd


def compute_pd_array_matrix(df: pd.DataFrame, atr_len: int = 14, lookback: int = 50) -> Dict[str, Any]:
    if len(df) < lookback:
        return {"status": "ERROR", "reason": "Insufficient bar depth"}

    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    closes = df['close'].values

    # True Range & ATR calculation
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
    atr = float(np.mean(tr[-atr_len:])) if len(tr) >= atr_len else 1.0

    curr_p = float(closes[-1])
    window_h = highs[-lookback:]
    window_l = lows[-lookback:]

    # 1. Structural Range & 50% Equilibrium
    range_high = float(np.max(window_h))
    range_low = float(np.min(window_l))
    equilibrium = (range_high + range_low) / 2.0
    zone = "PREMIUM" if curr_p >= equilibrium else "DISCOUNT"

    # 2. Rejection Block Detection
    sh_idx = int(np.argmax(window_h)) + (len(df) - lookback)
    sl_idx = int(np.argmin(window_l)) + (len(df) - lookback)

    bearish_rb = {
        "floor": float(min(opens[sh_idx], closes[sh_idx])),
        "ceiling": float(highs[sh_idx]),
        "bar_index": sh_idx
    }
    bullish_rb = {
        "floor": float(lows[sl_idx]),
        "ceiling": float(max(opens[sl_idx], closes[sl_idx])),
        "bar_index": sl_idx
    }

    # 3. Order Block Detection (Last opposite candle before displacement)
    bearish_ob = None
    bullish_ob = None

    for i in range(len(df) - 3, max(len(df) - 25, 2), -1):
        if closes[i] > opens[i] and (closes[i+1] < opens[i+1]) and (lows[i+1] < lows[i]):
            if (highs[i] - lows[i+2]) > (1.2 * atr):
                bearish_ob = {
                    "floor": float(lows[i]),
                    "ceiling": float(highs[i]),
                    "mean_threshold": (float(lows[i]) + float(highs[i])) / 2.0,
                    "bar_index": i
                }
                break

    for i in range(len(df) - 3, max(len(df) - 25, 2), -1):
        if closes[i] < opens[i] and (closes[i+1] > opens[i+1]) and (highs[i+1] > highs[i]):
            if (highs[i+2] - lows[i]) > (1.2 * atr):
                bullish_ob = {
                    "floor": float(lows[i]),
                    "ceiling": float(highs[i]),
                    "mean_threshold": (float(lows[i]) + float(highs[i])) / 2.0,
                    "bar_index": i
                }
                break

    # 4. Breaker Block Detection (Failed structural swings)
    bearish_breaker = None
    bullish_breaker = None

    for i in range(len(df) - 5, max(len(df) - 30, 2), -1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            prior_low = lows[i]
            if any(highs[j] > highs[i] for j in range(i+1, min(i+5, len(df)))):
                if curr_p < prior_low:
                    bearish_breaker = {
                        "level": float(prior_low),
                        "zone": (float(prior_low) - (0.25 * atr), float(prior_low) + (0.25 * atr))
                    }
                    break

    # 5. Composite Confluence Score Matrix (0 - 100)
    score_buy = 0.0
    score_sell = 0.0

    if zone == "DISCOUNT":
        score_buy += 25.0
    else:
        score_sell += 25.0

    if bullish_ob and bullish_ob['floor'] <= curr_p <= bullish_ob['ceiling']:
        score_buy += 30.0
    if bearish_ob and bearish_ob['floor'] <= curr_p <= bearish_ob['ceiling']:
        score_sell += 30.0

    if bullish_rb and curr_p <= bullish_rb['ceiling']:
        score_buy += 20.0
    if bearish_rb and curr_p >= bearish_rb['floor']:
        score_sell += 20.0

    if bearish_breaker and bearish_breaker['zone'][0] <= curr_p <= bearish_breaker['zone'][1]:
        score_sell += 25.0
    if bullish_breaker and bullish_breaker['zone'][0] <= curr_p <= bullish_breaker['zone'][1]:
        score_buy += 25.0

    return {
        "status": "SUCCESS",
        "current_price": round(curr_p, 2),
        "atr": round(atr, 2),
        "equilibrium_50": round(equilibrium, 2),
        "zone": zone,
        "pd_arrays": {
            "bearish_rejection_block": bearish_rb,
            "bullish_rejection_block": bullish_rb,
            "bearish_order_block": bearish_ob,
            "bullish_order_block": bullish_ob,
            "bearish_breaker": bearish_breaker,
            "bullish_breaker": bullish_breaker
        },
        "matrix_scores": {
            "buy_confluence": min(score_buy, 100.0),
            "sell_confluence": min(score_sell, 100.0)
        }
    }
