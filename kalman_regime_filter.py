"""
kalman_regime_filter.py — Terminal-Isolated 1D Scalar Kalman Fair-Value & Innovation Z-Score Engine
Calibrated separately for:
  - T1 (BTCUSD): High-wick crypto noise (elevated R_mult, smoothed drift Q_mult)
  - T2 (FX Majors/Crosses): NY Killzone impulse tracking (responsive Q_mult in 13-17 UTC)
  - T3 (XAUUSD): Bullion liquidity-regime adaptation (high R outside COMEX/NY overlap)
"""
from __future__ import annotations
import numpy as np

# Per-terminal calibration scaled relative to squared ATR(14) so parameters stay invariant across price levels
KALMAN_TERMINAL_PARAMS: dict[str, dict[str, float]] = {
    "T1": {
        "q_base": 0.045,        # Moderate drift so crypto trends are tracked without chasing noise
        "r_base": 0.420,        # Elevated measurement noise to absorb 0.35%-0.60% BTC stop-hunt wicks
        "ny_q_boost": 1.35,     # Slightly faster adaptation during US equity/ETF overlap (13-20 UTC)
        "off_r_boost": 1.40,    # Extra wick filtering during thin Asian crypto hours
        "climax_z": 2.40,       # Innovation Z-score threshold flagging overextended climax spikes
    },
    "T2": {
        "q_base": 0.065,        # Responsive fair-value drift during institutional FX killzones
        "r_base": 0.220,        # Lower tick noise on liquid FX pairs during active sessions
        "ny_q_boost": 1.60,     # Fast repricing during NY Killzone (13-17 UTC)
        "off_r_boost": 2.20,    # Heavy noise damping outside NY Killzone
        "climax_z": 2.10,       # Blocks exhaustion spikes (mirrors the 90%+ climax trap filter)
    },
    "T3": {
        "q_base": 0.055,        # Balanced bullion trend drift
        "r_base": 0.350,        # Absorbs routine $5-$10 gold stop runs
        "ny_q_boost": 1.75,     # High responsiveness during COMEX/NY bullion overlap (13-17 UTC)
        "off_r_boost": 2.50,    # Heavy damping during Asian gold rollover (21-07 UTC)
        "climax_z": 2.25,       # Flags parabolic gold exhaustion wicks
    },
}


def compute_kalman_fair_value(
    closes: np.ndarray,
    atr14: float,
    sleeve: str,
    utc_hour: int,
    spread_price: float = 0.0,
) -> dict[str, float | bool | str]:
    """
    Runs a 1D scalar Kalman filter over a 1D array of close prices.
    Scales Q and R by atr14^2 and live spread widening so parameters remain dimensionless.
    """
    n = len(closes)
    if n < 5 or atr14 <= 0.0:
        last_px = float(closes[-1]) if n > 0 else 0.0
        return {
            "fair_value": last_px,
            "gain": 0.5,
            "innovation": 0.0,
            "z_score": 0.0,
            "slope_atr": 0.0,
            "is_climax": False,
            "regime_bias": "NEUTRAL",
        }

    cfg = KALMAN_TERMINAL_PARAMS.get(sleeve, KALMAN_TERMINAL_PARAMS["T2"])
    in_ny_window = 13 <= utc_hour <= 17
    if sleeve == "T1":
        in_ny_window = 13 <= utc_hour <= 20

    q_mult = cfg["q_base"] * (cfg["ny_q_boost"] if in_ny_window else 0.75)
    r_mult = cfg["r_base"] * (1.0 if in_ny_window else cfg["off_r_boost"])

    # Inflate measurement noise R dynamically if broker spread widens relative to ATR
    spr_ratio = spread_price / max(atr14, 1e-9)
    if spr_ratio > 0.08:
        r_mult *= (1.0 + (spr_ratio - 0.08) * 6.0)

    var_scale = atr14 * atr14
    q = q_mult * var_scale
    r = r_mult * var_scale

    # Initialize state at first bar in window
    x_est = float(closes[0])
    p_est = r  # Initial state uncertainty equals 1 bar of measurement noise
    prev_x = x_est
    k_gain = 0.5
    innov = 0.0
    z_score = 0.0

    for idx in range(1, n):
        z_obs = float(closes[idx])

        # 1. Predict step: state persists, uncertainty grows by process drift Q
        x_pred = x_est
        p_pred = p_est + q

        # 2. Update step: compare observation against prediction
        innov = z_obs - x_pred
        s_var = p_pred + r  # Total innovation variance
        k_gain = p_pred / max(s_var, 1e-18)

        prev_x = x_est
        x_est = x_pred + k_gain * innov
        p_est = (1.0 - k_gain) * p_pred
        z_score = innov / max(float(np.sqrt(s_var)), 1e-9)

    slope_atr = (x_est - prev_x) / max(atr14, 1e-9)
    is_climax = abs(z_score) >= cfg["climax_z"]

    if z_score > 0.35 and slope_atr > 0.02 and not is_climax:
        regime_bias = "BULL_IMPULSE"
    elif z_score < -0.35 and slope_atr < -0.02 and not is_climax:
        regime_bias = "BEAR_IMPULSE"
    elif is_climax:
        regime_bias = "CLIMAX_EXHAUSTION"
    else:
        regime_bias = "EQUILIBRIUM"

    return {
        "fair_value": round(x_est, 6),
        "gain": round(k_gain, 3),
        "innovation": round(innov, 6),
        "z_score": round(z_score, 2),
        "slope_atr": round(slope_atr, 3),
        "is_climax": is_climax,
        "regime_bias": regime_bias,
    }
