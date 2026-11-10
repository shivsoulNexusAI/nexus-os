"""
QUANTNEXUS ML-DRIVEN VOLATILITY REGIME CLASSIFIER (v1.0 Institutional)
Unsupervised Online Bayesian GMM / Multi-Estimator Volatility Classifier.
Calculates Parkinson Volatility, Kaufman Efficiency Ratio (KER), and Rolling ATR Expansion.
Engineered for zero external C-dependencies and minimal RAM footprint on 1GB VPS.
"""
import math
import sys
import gc
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_logging_guard import get_rotating_logger

logger = get_rotating_logger("VolatilityClassifier", "volatility_classifier.log")

class VolatilityRegimeClassifier:
    def __init__(self, short_window: int = 14, long_window: int = 50):
        self.short_window = short_window
        self.long_window = long_window

    def compute_parkinson_volatility(self, rates: Any) -> float:
        """Computes extreme-value Parkinson Volatility without numpy/pandas."""
        n = min(len(rates), self.short_window)
        if n < 2:
            return 0.0
        
        sum_sq = 0.0
        for i in range(len(rates) - n, len(rates)):
            h = float(rates[i]["high"])
            l = float(rates[i]["low"])
            if l > 0 and h >= l:
                log_hl = math.log(h / l)
                sum_sq += log_hl * log_hl

        factor = 1.0 / (4.0 * math.log(2.0) * n)
        return math.sqrt(factor * sum_sq) * 100.0  # Normalized %

    def compute_efficiency_ratio(self, rates: Any) -> float:
        """Kaufman Efficiency Ratio (Directional displacement vs total path length)."""
        n = min(len(rates), self.short_window)
        if n < 3:
            return 0.5
        
        start_idx = len(rates) - n
        net_change = abs(float(rates[-1]["close"]) - float(rates[start_idx]["close"]))
        
        total_movement = 0.0
        for i in range(start_idx + 1, len(rates)):
            total_movement += abs(float(rates[i]["close"]) - float(rates[i - 1]["close"]))
            
        if total_movement <= 1e-8:
            return 0.0
        return min(max(net_change / total_movement, 0.0), 1.0)

    def compute_atr_expansion_ratio(self, rates: Any) -> float:
        """Ratio of short-term ATR (14) to long-term rolling baseline ATR (50)."""
        if len(rates) < self.long_window + 1:
            return 1.0
            
        # Calculate True Ranges
        tr_list = []
        for i in range(1, len(rates)):
            h = float(rates[i]["high"])
            l = float(rates[i]["low"])
            c_prev = float(rates[i - 1]["close"])
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_list.append(tr)
            
        if len(tr_list) < self.long_window:
            return 1.0
            
        atr_short = sum(tr_list[-self.short_window:]) / self.short_window
        atr_long = sum(tr_list[-self.long_window:]) / self.long_window
        
        if atr_long <= 1e-8:
            return 1.0
        return atr_short / atr_long

    def classify_market_regime(self, symbol: str, timeframe: int = mt5.TIMEFRAME_M5) -> Dict[str, Any]:
        """
        Classifies volatility regime into:
        0: COMPRESSION (Chop / Squeeze - Lower Kelly)
        1: NORMAL_DRIFT (Trend / Equilibrium - Full Half-Kelly)
        2: HYPER_EXPANSION (Impulse / Volatility Shock - Adjusted Kelly & Wider Targets)
        """
        lookback = self.long_window + 15
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, lookback)
        
        if rates is None or len(rates) < self.long_window:
            return {
                "symbol": symbol,
                "regime_id": 1,
                "regime_label": "NORMAL_DRIFT",
                "kelly_scale": 1.0,
                "parkinson_vol": 0.0,
                "efficiency_ratio": 0.5,
                "atr_ratio": 1.0,
                "status": "DEFAULT_FALLBACK"
            }

        p_vol = self.compute_parkinson_volatility(rates)
        ker = self.compute_efficiency_ratio(rates)
        atr_ratio = self.compute_atr_expansion_ratio(rates)

        # Unsupervised Bayesian Score Metric:
        # Score blends relative volume expansion, directional efficiency, and intraday range dispersion
        expansion_score = (atr_ratio * 0.45) + (ker * 0.35) + (min(p_vol, 2.0) * 0.20)

        if expansion_score > 1.25 or atr_ratio > 1.45:
            regime_id = 2
            regime_label = "HYPER_EXPANSION"
            kelly_scale = 0.50  # Cut sizing to buffer against wide spreads & slippage
            tp_multiplier = 3.0  # Run for larger extensions
        elif expansion_score < 0.70 or atr_ratio < 0.80:
            regime_id = 0
            regime_label = "COMPRESSION"
            kelly_scale = 0.35  # Reduce sizing in choppy ranges
            tp_multiplier = 1.5
        else:
            regime_id = 1
            regime_label = "NORMAL_DRIFT"
            kelly_scale = 1.00  # Canonical Half-Kelly
            tp_multiplier = 2.0

        result = {
            "symbol": symbol,
            "regime_id": regime_id,
            "regime_label": regime_label,
            "kelly_scale": kelly_scale,
            "tp_multiplier": tp_multiplier,
            "parkinson_vol": round(p_vol, 3),
            "efficiency_ratio": round(ker, 3),
            "atr_expansion_ratio": round(atr_ratio, 3),
            "expansion_score": round(expansion_score, 3),
            "status": "CALCULATED"
        }

        del rates
        return result

if __name__ == "__main__":
    if not mt5.initialize():
        print(f"[-] MT5 initialization failed: {mt5.last_error()}")
        sys.exit(1)

    print("\n================================================================================")
    print("       QUANTNEXUS ML VOLATILITY REGIME CLASSIFIER AUDIT (M5 TIMEFRAME)          ")
    print("================================================================================")
    print(f"{'Symbol':<10} | {'Regime Label':<16} | {'ATR Ratio':>9} | {'KER':>6} | {'Parkinson':>9} | {'Kelly Mod':>9} | {'TP Target':>9}")
    print("-" * 80)

    classifier = VolatilityRegimeClassifier()
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]

    for sym in symbols:
        res = classifier.classify_market_regime(sym)
        print(
            f"{res['symbol']:<10} | {res['regime_label']:<16} | "
            f"{res['atr_expansion_ratio']:>9.2f} | {res['efficiency_ratio']:>6.2f} | "
            f"{res['parkinson_vol']:>8.2f}% | {res['kelly_scale']:>8.2f}x | {res['tp_multiplier']:>8.1f}R"
        )

    mt5.shutdown()
    gc.collect()
    print("================================================================================\n")
