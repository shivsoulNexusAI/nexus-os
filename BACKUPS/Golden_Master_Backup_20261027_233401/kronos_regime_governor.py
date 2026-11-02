"""
KRONOS INSTITUTIONAL REGIME GOVERNOR (NEURAL & VPIN INTEGRATED)
Harmonizes model/kronos.py, sentinel_vpin.py, and spread_guard.py
"""
import os
import sys
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Any

# Dynamic resolution of local model and tools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Optional VPIN & Spread Guard hooks
try:
    from sentinel_vpin import VPINCalculator
    HAS_VPIN = True
except ImportError:
    HAS_VPIN = False

try:
    from spread_guard import SpreadGuard
    HAS_SPREAD = True
except ImportError:
    HAS_SPREAD = False

class KronosRegimeEngine:
    def __init__(self, confidence_cutoff: float = 0.80):
        self.cutoff = confidence_cutoff
        self.regimes = ["CLEAN_TREND", "RANGE_EXPANSION", "ACCUMULATION", "HIGH_VOLATILITY_CHOP"]
        self.vpin_engine = VPINCalculator() if HAS_VPIN else None
        self.spread_guard = SpreadGuard() if HAS_SPREAD else None

    def extract_features(self, df_rates: pd.DataFrame) -> Dict[str, float]:
        if len(df_rates) < 30:
            return {"volatility_ratio": 1.0, "efficiency_ratio": 0.5, "volume_imbalance": 0.0, "momentum_drift": 0.0, "vpin_toxicity": 0.20}

        closes = df_rates['close'].to_numpy(dtype=float)
        highs = df_rates['high'].to_numpy(dtype=float)
        lows = df_rates['low'].to_numpy(dtype=float)
        volumes = df_rates['tick_volume'].to_numpy(dtype=float) if 'tick_volume' in df_rates else np.ones(len(closes))

        # 1. Kaufman Efficiency Ratio
        direction = abs(closes[-1] - closes[-20])
        volatility = np.sum(np.abs(np.diff(closes[-20:])))
        er = float(direction / volatility) if volatility > 0 else 0.0

        # 2. Volatility Ratio (Fast vs Slow ATR)
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
        atr_fast = np.mean(tr[-10:]) if len(tr) >= 10 else 1.0
        atr_slow = np.mean(tr[-30:]) if len(tr) >= 30 else 1.0
        vol_ratio = float(atr_fast / atr_slow) if atr_slow > 0 else 1.0

        # 3. Order Flow Imbalance
        price_diff = np.diff(closes)
        up_vol = np.sum(volumes[1:][price_diff > 0])
        down_vol = np.sum(volumes[1:][price_diff < 0])
        total_vol = up_vol + down_vol
        vol_imbalance = float((up_vol - down_vol) / total_vol) if total_vol > 0 else 0.0

        # 4. Microstructure VPIN Toxicity Proxy
        vpin_toxicity = 0.20
        if self.vpin_engine and hasattr(self.vpin_engine, "calculate"):
            try:
                vpin_toxicity = float(self.vpin_engine.calculate(df_rates))
            except Exception:
                pass
        else:
            abs_imb = abs(vol_imbalance)
            vpin_toxicity = float(0.15 + (abs_imb * 0.35) + (vol_ratio > 1.30) * 0.25)

        # 5. Momentum Drift
        returns = np.diff(np.log(closes[-25:]))
        drift_z = float(np.mean(returns) / (np.std(returns) + 1e-8)) * np.sqrt(25)

        return {
            "volatility_ratio": vol_ratio,
            "efficiency_ratio": er,
            "volume_imbalance": vol_imbalance,
            "vpin_toxicity": vpin_toxicity,
            "momentum_drift": drift_z
        }

    def evaluate_setup(self, symbol: str, direction: str, df_rates: pd.DataFrame, current_spread: float = 0.0) -> Tuple[bool, str, float, str]:
        # Spread Guard Gating
        if self.spread_guard and hasattr(self.spread_guard, "is_spread_valid"):
            if not self.spread_guard.is_spread_valid(symbol, current_spread):
                return False, "SPREAD_BLOCKED", 0.0, f"VETO: Spread ({current_spread}) exceeds institutional threshold."

        feats = self.extract_features(df_rates)
        er = feats["efficiency_ratio"]
        vr = feats["volatility_ratio"]
        imb = feats["volume_imbalance"]
        tox = feats["vpin_toxicity"]

        # VPIN Toxicity Check (> 0.65 indicates informed adverse selection)
        if tox > 0.65:
            return False, "TOXIC_ORDER_FLOW", 0.45, f"VETO: VPIN toxicity spike ({tox:.2f} > 0.65). Execution suppressed."

        base_score = 0.65
        if er >= 0.45: base_score += 0.15
        elif er < 0.25: base_score -= 0.15

        if direction.upper() in ["BUY", "LONG"] and imb > 0.10: base_score += 0.10
        elif direction.upper() in ["SELL", "SHORT"] and imb < -0.10: base_score += 0.10
        elif (direction.upper() in ["BUY", "LONG"] and imb < -0.20) or (direction.upper() in ["SELL", "SHORT"] and imb > 0.20): base_score -= 0.15

        edge_score = float(np.clip(base_score, 0.40, 0.96))

        if vr > 1.45:
            regime = "HIGH_VOLATILITY_CHOP"
        elif er > 0.40:
            regime = "CLEAN_TREND"
        elif vr < 0.75:
            regime = "ACCUMULATION"
        else:
            regime = "RANGE_EXPANSION"

        if regime == "HIGH_VOLATILITY_CHOP":
            return False, regime, edge_score, "VETO: Outlier chop volatility detected (ATR expansion unstable)"
        
        if edge_score < self.cutoff:
            return False, regime, edge_score, f"VETO: Edge score {edge_score*100:.1f}% below institutional floor ({self.cutoff*100:.1f}%)"

        return True, regime, edge_score, "APPROVED: Gating nominal"

governor = KronosRegimeEngine(confidence_cutoff=0.80)
