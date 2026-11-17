"""
kalman_regime_filter.py — Terminal-Isolated 4-Model Market Microstructure Engine:
  1. 1D Scalar Kalman Filter (Fair Value & Innovation Z-Score)
  2. Glosten-Milgrom (1985) Adverse-Selection Toxicity Efficiency (tVPIN / SprATR)
  3. Avellaneda-Stoikov (2008) Reservation-Price Skew & Dealer Inventory Pressure
  4. Dealer Gamma-Regime Variance Ratio (Long-Gamma Strike Pinning vs. Short-Gamma Cascade)
"""
from __future__ import annotations
import numpy as np

KALMAN_TERMINAL_PARAMS: dict[str, dict[str, float]] = {
    "T1": {
        "q_base": 0.045,        # Moderate drift so crypto trends are tracked without chasing noise
        "r_base": 0.420,        # Elevated measurement noise to absorb 0.35%-0.60% BTC stop-hunt wicks
        "ny_q_boost": 1.35,     # Faster adaptation during US equity/ETF overlap (13-20 UTC)
        "off_r_boost": 1.40,    # Extra wick filtering during thin Asian crypto hours
        "climax_z": 2.40,       # Innovation Z-score threshold flagging overextended climax spikes
        "min_tvpin": 0.50,      # Glosten-Milgrom minimum informed order-flow toxicity
        "min_tox_eff": 5.0,     # Glosten-Milgrom minimum tVPIN / SprATR efficiency
        "prime_tox_eff": 8.0,   # High-efficiency informed flow before dealer spread widening
        "as_gamma": 0.45,       # Avellaneda-Stoikov dealer risk aversion (gamma)
        "as_tau": 1.00,         # Normalized remaining inventory horizon (tau)
        "max_as_skew_atr": 0.55,# Max reservation-price skew in ATR units before dealer inventory flush
        "pin_vr": 0.62,         # Variance ratio below which dealers are long-gamma pinning price
        "cascade_vr": 1.55,     # Variance ratio above which dealers are short-gamma delta-hedging
    },
    "T2": {
        "q_base": 0.065,        # Responsive fair-value drift during institutional FX killzones
        "r_base": 0.220,        # Lower tick noise on liquid FX pairs during active sessions
        "ny_q_boost": 1.60,     # Fast repricing during NY Killzone (13-17 UTC)
        "off_r_boost": 2.20,    # Heavy noise damping outside NY Killzone
        "climax_z": 2.10,       # Blocks exhaustion spikes
        "min_tvpin": 0.52,
        "min_tox_eff": 4.2,
        "prime_tox_eff": 7.0,
        "as_gamma": 0.65,
        "as_tau": 0.85,
        "max_as_skew_atr": 0.42,
        "pin_vr": 0.68,
        "cascade_vr": 1.45,
    },
    "T3": {
        "q_base": 0.055,        # Balanced bullion trend drift
        "r_base": 0.350,        # Absorbs routine $5-$10 gold stop runs
        "ny_q_boost": 1.75,     # High responsiveness during COMEX/NY bullion overlap (13-17 UTC)
        "off_r_boost": 2.50,    # Heavy damping during Asian gold rollover (21-07 UTC)
        "climax_z": 2.25,       # Flags parabolic gold exhaustion wicks
        "min_tvpin": 0.54,
        "min_tox_eff": 4.8,
        "prime_tox_eff": 7.5,
        "as_gamma": 0.55,
        "as_tau": 0.90,
        "max_as_skew_atr": 0.48,
        "pin_vr": 0.65,
        "cascade_vr": 1.50,
    },
}


def compute_kalman_fair_value(
    closes: np.ndarray,
    atr14: float,
    sleeve: str,
    utc_hour: int,
    spread_price: float = 0.0,
    tvpin: float = 0.55,
) -> dict[str, float | bool | str]:
    """
    Evaluates:
      - 1D scalar Kalman fair value & Innovation Z-score
      - Glosten-Milgrom (1985) Adverse-Selection Toxicity Ratio (tVPIN / SprATR)
      - Avellaneda-Stoikov (2008) Reservation-Price Skew (r = s - q * gamma * sigma^2 * tau)
      - Dealer Gamma-Regime Variance Ratio (short-window vs. long-window realized variance)
    """
    n = len(closes)
    if n < 12 or atr14 <= 0.0:
        last_px = float(closes[-1]) if n > 0 else 0.0
        return {
            "fair_value": last_px,
            "gain": 0.5,
            "innovation": 0.0,
            "z_score": 0.0,
            "slope_atr": 0.0,
            "is_climax": False,
            "regime_bias": "NEUTRAL",
            "tox_eff": 0.0,
            "gm_state": "NO_DATA",
            "mm_taxed": False,
            "as_res_px": last_px,
            "as_skew_atr": 0.0,
            "as_half_spr_atr": 0.0,
            "as_state": "NO_DATA",
            "inv_flush_risk": False,
            "gamma_vr": 1.0,
            "gamma_regime": "GAMMA_NEUTRAL",
            "is_gamma_pinned": False,
        }

    cfg = KALMAN_TERMINAL_PARAMS.get(sleeve, KALMAN_TERMINAL_PARAMS["T2"])
    in_ny_window = (13 <= utc_hour <= 20) if sleeve == "T1" else (13 <= utc_hour <= 17)

    # 4. Pre-compute Gamma-Regime Variance Ratio (last 8 bars vs. full baseline window)
    all_diffs = np.diff(closes)
    short_diffs = all_diffs[-8:]
    var_long = float(np.var(all_diffs, ddof=1)) if len(all_diffs) > 2 else (atr14 * 0.35) ** 2
    var_short = float(np.var(short_diffs, ddof=1)) if len(short_diffs) > 2 else var_long
    gamma_vr = var_short / max(var_long, 1e-18)

    is_gamma_pinned = gamma_vr <= cfg["pin_vr"]
    if is_gamma_pinned:
        gamma_regime = "LONG_GAMMA_PIN"
    elif gamma_vr >= cfg["cascade_vr"]:
        gamma_regime = "SHORT_GAMMA_CASCADE"
    else:
        gamma_regime = "GAMMA_NEUTRAL"

    # Adapt Kalman Q/R by session liquidity and dealer gamma regime
    q_mult = cfg["q_base"] * (cfg["ny_q_boost"] if in_ny_window else 0.75)
    r_mult = cfg["r_base"] * (1.0 if in_ny_window else cfg["off_r_boost"])
    if is_gamma_pinned:
        q_mult *= 0.70   # Damp fair-value drift when dealers are pinning strike
        r_mult *= 1.35
    elif gamma_regime == "SHORT_GAMMA_CASCADE":
        q_mult *= 1.30   # Accelerate fair-value tracking during forced delta-hedging

    spr_ratio = spread_price / max(atr14, 1e-9)
    if spr_ratio > 0.08:
        r_mult *= (1.0 + (spr_ratio - 0.08) * 6.0)

    var_scale = atr14 * atr14
    q = q_mult * var_scale
    r = r_mult * var_scale

    x_est = float(closes[0])
    p_est = r
    prev_x = x_est
    k_gain = 0.5
    innov = 0.0
    z_score = 0.0

    for idx in range(1, n):
        z_obs = float(closes[idx])
        x_pred = x_est
        p_pred = p_est + q

        innov = z_obs - x_pred
        s_var = p_pred + r
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

    # Glosten-Milgrom (1985) Adverse-Selection Toxicity Ratio
    eff_denom = max(spr_ratio, 0.015)
    tox_eff = float(tvpin) / eff_denom
    mm_taxed = (float(tvpin) < cfg["min_tvpin"]) or (tox_eff < cfg["min_tox_eff"])

    if mm_taxed:
        gm_state = "MM_TAXED"
    elif tox_eff >= cfg["prime_tox_eff"]:
        gm_state = "FRONT_RUN_FLOW"
    else:
        gm_state = "INFORMED_WINDOW"

    # Avellaneda-Stoikov (2008) Reservation-Price Skew & Quote Pressure
    recent_diffs = all_diffs[-min(len(all_diffs), 20):]
    sigma_px = float(np.std(recent_diffs)) if len(recent_diffs) > 1 else atr14 * 0.35
    sigma_atr_sq = (sigma_px / max(atr14, 1e-9)) ** 2

    weights = np.exp(np.linspace(-1.5, 0.0, len(recent_diffs)))
    norm_moves = np.clip(recent_diffs / max(atr14, 1e-9), -2.5, 2.5)
    crowd_wave = float(np.sum(weights * norm_moves) / max(np.sum(weights), 1e-9))
    q_dealer = -crowd_wave * (0.6 + 0.8 * float(tvpin))

    gamma = cfg["as_gamma"]
    tau = cfg["as_tau"]
    as_skew_atr = -q_dealer * gamma * sigma_atr_sq * tau * 4.0
    as_res_px = float(closes[-1]) + (as_skew_atr * atr14)
    as_half_spr_atr = 0.5 * gamma * sigma_atr_sq * tau * 2.5
    inv_flush_risk = abs(as_skew_atr) >= cfg["max_as_skew_atr"]

    if inv_flush_risk:
        as_state = "INV_FLUSH_RISK"
    elif abs(as_skew_atr) >= cfg["max_as_skew_atr"] * 0.55:
        as_state = "DEALER_SKEWING"
    else:
        as_state = "BALANCED_BOOK"

    return {
        "fair_value": round(x_est, 6),
        "gain": round(k_gain, 3),
        "innovation": round(innov, 6),
        "z_score": round(z_score, 2),
        "slope_atr": round(slope_atr, 3),
        "is_climax": is_climax,
        "regime_bias": regime_bias,
        "tox_eff": round(tox_eff, 2),
        "gm_state": gm_state,
        "mm_taxed": mm_taxed,
        "as_res_px": round(as_res_px, 6),
        "as_skew_atr": round(as_skew_atr, 3),
        "as_half_spr_atr": round(as_half_spr_atr, 3),
        "as_state": as_state,
        "inv_flush_risk": inv_flush_risk,
        "gamma_vr": round(gamma_vr, 3),
        "gamma_regime": gamma_regime,
        "is_gamma_pinned": is_gamma_pinned,
    }
