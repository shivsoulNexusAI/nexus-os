import numpy as np

def detect_smc_ob_ifvg(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    poc: float,
    vah: float,
    val: float,
    atr: float,
) -> dict:
    """
    Strict Institutional Order Block + Inversion Fair Value Gap (IFVG) detector:
    1. Minimum FVG gap >= 0.40 * ATR (filters micro-noise)
    2. Inversion candle body >= 1.30 * ATR (true displacement)
    3. Mandatory Volume Profile (POC / VAH / VAL) structural alignment (<= 0.50 * ATR)
    """
    n = len(closes)
    if n < 15 or atr <= 0:
        return {"tag": "NONE", "dir": "FLAT", "bonus": 0.0, "entry_mid": 0.0, "sl_px": 0.0, "tp_mult": 3.0}

    curr_close = float(closes[-1])
    curr_high = float(highs[-1])
    curr_low = float(lows[-1])
    min_gap = atr * 0.40
    min_disp = atr * 1.30

    # 1. BEARISH OB + IFVG + VP
    for k in range(n - 5, max(2, n - 14), -1):
        if (lows[k] - highs[k - 2]) >= min_gap:
            fvg_top = float(lows[k])
            fvg_bot = float(highs[k - 2])
            inv_bars = [
                m for m in range(k + 1, n - 1)
                if closes[m] < fvg_bot and (opens[m] - closes[m]) >= min_disp
            ]
            if not inv_bars:
                continue
            inv_idx = inv_bars[0]
            ob_candidates = [j for j in range(max(0, inv_idx - 3), inv_idx + 1) if closes[j] > opens[j]]
            if not ob_candidates:
                continue
            ob_idx = ob_candidates[-1]
            ob_high = float(highs[ob_idx])
            ob_low = float(opens[ob_idx])

            zone_low = min(fvg_bot, ob_low)
            zone_high = max(fvg_top, ob_high)
            in_retest = (curr_high >= zone_low) and (curr_close <= ob_high) and (curr_close < float(opens[-1]))
            vp_aligned = abs(zone_high - poc) <= atr * 0.50 or abs(zone_high - vah) <= atr * 0.50

            if in_retest and vp_aligned:
                return {
                    "tag": "OB+IFVG+VP",
                    "dir": "SELL",
                    "bonus": 15.0,
                    "entry_mid": round((fvg_top + fvg_bot) * 0.5, 6),
                    "sl_px": round(ob_high + atr * 0.25, 6),
                    "tp_mult": 4.0,
                }

    # 2. BULLISH OB + IFVG + VP
    for k in range(n - 5, max(2, n - 14), -1):
        if (lows[k - 2] - highs[k]) >= min_gap:
            fvg_top = float(lows[k - 2])
            fvg_bot = float(highs[k])
            inv_bars = [
                m for m in range(k + 1, n - 1)
                if closes[m] > fvg_top and (closes[m] - opens[m]) >= min_disp
            ]
            if not inv_bars:
                continue
            inv_idx = inv_bars[0]
            ob_candidates = [j for j in range(max(0, inv_idx - 3), inv_idx + 1) if closes[j] < opens[j]]
            if not ob_candidates:
                continue
            ob_idx = ob_candidates[-1]
            ob_low = float(lows[ob_idx])
            ob_high = float(opens[ob_idx])

            zone_low = min(fvg_bot, ob_low)
            zone_high = max(fvg_top, ob_high)
            in_retest = (curr_low <= zone_high) and (curr_close >= ob_low) and (curr_close > float(opens[-1]))
            vp_aligned = abs(zone_low - poc) <= atr * 0.50 or abs(zone_low - val) <= atr * 0.50

            if in_retest and vp_aligned:
                return {
                    "tag": "OB+IFVG+VP",
                    "dir": "BUY",
                    "bonus": 15.0,
                    "entry_mid": round((fvg_top + fvg_bot) * 0.5, 6),
                    "sl_px": round(ob_low - atr * 0.25, 6),
                    "tp_mult": 4.0,
                }

    return {"tag": "NONE", "dir": "FLAT", "bonus": 0.0, "entry_mid": 0.0, "sl_px": 0.0, "tp_mult": 3.0}
