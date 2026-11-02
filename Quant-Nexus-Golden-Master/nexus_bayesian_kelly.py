"""
NEXUS BAYESIAN KELLY // ONLINE EXPECTANCY ESTIMATOR & POSTERIOR ALLOCATION ENGINE
"""
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

PRIOR_ALPHA = 12.0  # Equivalent to 12 prior wins
PRIOR_BETA = 8.0    # Equivalent to 8 prior losses (60% baseline prior)
DECAY_LAMBDA = 0.96 # Exponential regime decay factor (~25-trade effective memory)

def evaluate_bayesian_kelly():
    """
    Computes online Bayesian posterior win probability, empirical payoff ratio,
    and conservative 10th-percentile dynamic Quarter-Kelly sizing scalar.
    Returns: (can_execute: bool, bayes_multiplier: float, reason: str, metrics: dict)
    """
    if not mt5.initialize():
        return True, 1.0, "MT5 bypass", {}

    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=14)

    deals = mt5.history_deals_get(from_date, now)
    if not deals:
        return True, 1.0, "No recent history; using baseline prior", {"mean_win_rate": 0.60}

    # Filter closed trades executed by the fleet
    out_deals = [
        d for d in deals 
        if d.entry == mt5.DEAL_ENTRY_OUT and d.magic in [777901, 777902, 777903, 999999, 0]
    ]

    if len(out_deals) < 5:
        return True, 1.0, "Insufficient deals for posterior convergence; baseline sizing active", {"deals_count": len(out_deals)}

    # Sort chronological
    out_deals.sort(key=lambda x: x.time)

    alpha = PRIOR_ALPHA
    beta = PRIOR_BETA
    wins = []
    losses = []

    for d in out_deals:
        pnl = d.profit + d.swap + d.commission
        if pnl > 0:
            alpha = (DECAY_LAMBDA * alpha) + 1.0
            beta = (DECAY_LAMBDA * beta)
            wins.append(pnl)
        elif pnl < 0:
            alpha = (DECAY_LAMBDA * alpha)
            beta = (DECAY_LAMBDA * beta) + 1.0
            losses.append(abs(pnl))

    # Calculate empirical payoff ratio b = avg_win / avg_loss
    avg_win = float(np.mean(wins)) if wins else 50.0
    avg_loss = float(np.mean(losses)) if losses else 30.0
    payoff_b = max(0.8, avg_win / max(avg_loss, 1.0))

    # Posterior Beta Distribution Statistics
    mean_p = alpha / (alpha + beta)
    var_p = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1.0))
    std_p = np.sqrt(max(1e-6, var_p))

    # 10th percentile conservative credible win-rate (z = -1.2816)
    p_cred = float(np.clip(mean_p - (1.2816 * std_p), 0.10, 0.90))

    # Dynamic Kelly formula: f* = (p(b+1) - 1) / b
    kelly_full = (p_cred * (payoff_b + 1.0) - 1.0) / payoff_b
    quarter_kelly = max(0.0, kelly_full * 0.25)

    # Baseline theoretical Quarter-Kelly (p=0.60, b=1.6 -> f* = 0.35 -> QK = ~0.0875)
    baseline_qk = 0.0875
    bayes_multiplier = round(float(np.clip(quarter_kelly / baseline_qk, 0.0, 1.60)), 2)

    metrics = {
        "alpha": round(alpha, 2),
        "beta": round(beta, 2),
        "mean_win_rate_pct": round(mean_p * 100, 1),
        "credible_win_rate_pct": round(p_cred * 100, 1),
        "payoff_ratio": round(payoff_b, 2),
        "quarter_kelly_pct": round(quarter_kelly * 100, 2),
        "sizing_multiplier": bayes_multiplier
    }

    # Zero or negative expectancy veto
    if kelly_full <= 0:
        return False, 0.0, f"Negative expectancy regime (Credible Win-Rate {p_cred*100:.1f}%, Payoff {payoff_b:.2f} -> f* <= 0)", metrics

    return True, bayes_multiplier, f"Bayesian Kelly active: Credible p={p_cred*100:.1f}%, b={payoff_b:.2f} -> {bayes_multiplier}x size", metrics
