"""
QuantNexus V3.1 - VPIN & Microstructure Toxicity Engine
"""
import numpy as np

def calculate_toxicity_metrics(ticks):
    """
    Evaluates tick arrival intensity (lambda_t) and signed buyer/seller tick imbalance.
    """
    if ticks is None or len(ticks) < 50:
        return {"toxicity_score": 0.0, "lambda_spike": False, "signed_delta": 0.0}

    bids = ticks['bid']
    asks = ticks['ask']
    prices = 0.5 * (bids + asks)
    
    price_diffs = np.diff(prices)
    signs = np.zeros_like(price_diffs)
    signs[price_diffs > 0] = 1
    signs[price_diffs < 0] = -1
    for i in range(1, len(signs)):
        if signs[i] == 0:
            signs[i] = signs[i-1]

    signed_delta = float(np.sum(signs)) / max(1.0, float(len(signs)))
    
    if 'time_msc' in ticks.dtype.names:
        times = ticks['time_msc']
    else:
        times = ticks['time'] * 1000.0

    recent_window_ticks = np.sum(times >= (times[-1] - 5000))
    baseline_rate_per_5s = len(times) / (max(1.0, (times[-1] - times[0]) / 5000.0))
    lambda_spike = recent_window_ticks > (3.5 * baseline_rate_per_5s)

    toxicity_score = abs(signed_delta) * (2.0 if lambda_spike else 1.0)

    return {
        "toxicity_score": round(toxicity_score, 4),
        "lambda_spike": bool(lambda_spike),
        "signed_delta": round(signed_delta, 4)
    }
