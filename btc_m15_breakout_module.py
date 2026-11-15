import numpy as np

def detect_btc_m15_breakout(
    o15: np.ndarray,
    h15: np.ndarray,
    l15: np.ndarray,
    c15: np.ndarray,
    v15: np.ndarray,
    atr15: float,
    h1_bull: bool,
    h1_bear: bool,
) -> dict:
    """
    Dedicated T1 BTCUSD M15 Trend-Displacement Breakout Detector:
    1. H1 EMA21/EMA55 macro trend alignment
    2. 16-bar M15 (4-hour) Donchian structural close breakout
    3. Displacement candle body >= 1.25 * M15 ATR + strong close location (top/bottom 25%)
    4. Tick volume surge >= 1.35x 20-bar M15 average + Volume Profile VAH/VAL clearance
    """
    n = len(c15)
    if n < 35 or atr15 <= 0:
        return {"tag": "NONE", "dir": "FLAT", "conf": 0.0, "sl_dist": 0.0, "tp_mult": 3.5}

    curr_o = float(o15[-1])
    curr_h = float(h15[-1])
    curr_l = float(l15[-1])
    curr_c = float(c15[-1])
    curr_v = float(v15[-1])
    bar_rng = max(1e-9, curr_h - curr_l)
    body = abs(curr_c - curr_o)

    # 16-bar M15 (4H) structural range excluding current bar
    donch_hi = float(np.max(h15[-17:-1]))
    donch_lo = float(np.min(l15[-17:-1]))

    # 32-bar M15 Volume Profile VAH / VAL
    win_c = c15[-33:-1]
    val = float(np.percentile(win_c, 25))
    vah = float(np.percentile(win_c, 75))

    avg_vol = max(1.0, float(np.mean(v15[-21:-1])))
    vol_ratio = curr_v / avg_vol

    # Minimum institutional displacement & volume thresholds
    if body < atr15 * 1.25 or vol_ratio < 1.35:
        return {"tag": "NONE", "dir": "FLAT", "conf": 0.0, "sl_dist": 0.0, "tp_mult": 3.5}

    # Bullish M15 Trend-Displacement Breakout
    close_pos_bull = (curr_c - curr_l) / bar_rng
    if h1_bull and curr_c > curr_o and curr_c > donch_hi and curr_c > vah and close_pos_bull >= 0.75:
        conf = 84.0
        if vol_ratio >= 1.75:
            conf += 3.0
        if body >= atr15 * 1.65:
            conf += 3.0
        return {
            "tag": "BTC-M15-BRK",
            "dir": "BUY",
            "conf": round(min(94.0, conf), 1),
            "sl_dist": round(atr15 * 2.2, 2),
            "tp_mult": 3.5,
        }

    # Bearish M15 Trend-Displacement Breakout
    close_pos_bear = (curr_h - curr_c) / bar_rng
    if h1_bear and curr_c < curr_o and curr_c < donch_lo and curr_c < val and close_pos_bear >= 0.75:
        conf = 84.0
        if vol_ratio >= 1.75:
            conf += 3.0
        if body >= atr15 * 1.65:
            conf += 3.0
        return {
            "tag": "BTC-M15-BRK",
            "dir": "SELL",
            "conf": round(min(94.0, conf), 1),
            "sl_dist": round(atr15 * 2.2, 2),
            "tp_mult": 3.5,
        }

    return {"tag": "NONE", "dir": "FLAT", "conf": 0.0, "sl_dist": 0.0, "tp_mult": 3.5}
