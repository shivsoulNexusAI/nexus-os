import os

code = """# -*- coding: utf-8 -*-
import math
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone

class ApexMicrostructureML:
    @staticmethod
    def extract_features(symbol: str):
        # 1. Microstructure Rates (M5)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 20:
            return None

        # Garman-Klass Volatility
        gk_elements = []
        for r in rates[-14:]:
            o, h, l, c = r['open'], r['high'], r['low'], r['close']
            if o <= 0 or l <= 0: continue
            term1 = 0.5 * (math.log(h / l) ** 2)
            term2 = (2.0 * math.log(2.0) - 1.0) * (math.log(c / o) ** 2)
            gk_elements.append(term1 - term2)
        gk_vol = math.sqrt(sum(gk_elements) / len(gk_elements)) if gk_elements else 0.001

        # 2. Aldemon Liquidity Penetration & High-Low Wick Dynamics
        recent_high = max(r['high'] for r in rates[-20:-2])
        recent_low = min(r['low'] for r in rates[-20:-2])
        curr = rates[-1]
        prev = rates[-2]
        atr = sum(r['high'] - r['low'] for r in rates[-14:]) / 14.0
        if atr <= 0:
            atr = curr['close'] * 0.001

        sweep_depth_pts = 0.0
        bias = "NEUTRAL"

        # Check for sweeps
        if prev['low'] < recent_low and curr['close'] > recent_low:
            bias = "BULLISH_SWEEP"
            sweep_depth_pts = (recent_low - prev['low']) / atr
        elif prev['high'] > recent_high and curr['close'] < recent_high:
            bias = "BEARISH_SWEEP"
            sweep_depth_pts = (prev['high'] - recent_high) / atr
        else:
            # Momentum Micro-Bias (M1/M5 close slope)
            if curr['close'] > rates[-3]['close']:
                bias = "MOMENTUM_LONG"
            elif curr['close'] < rates[-3]['close']:
                bias = "MOMENTUM_SHORT"

        # 3. Robust Tick Flow & Order Flow Imbalance (OFI)
        # Fetch latest 150 ticks using 0 offset (backwards from current live tick)
        ticks = mt5.copy_ticks_from(symbol, 0, 150, mt5.COPY_TICKS_ALL)
        ofi_delta = 0.0
        spread_ratio = 1.0

        if ticks is not None and len(ticks) >= 15:
            # Measure directional tick velocity
            mid_prices = (ticks['bid'] + ticks['ask']) / 2.0
            price_deltas = np.diff(mid_prices)
            up_moves = np.sum(price_deltas[price_deltas > 0])
            down_moves = np.abs(np.sum(price_deltas[price_deltas < 0]))
            tot_moves = up_moves + down_moves
            
            if tot_moves > 0:
                ofi_delta = float((up_moves - down_moves) / tot_moves)
            else:
                ofi_delta = 0.0

            # Spread ratio to detect institutional compression/expansion
            spreads = ticks['ask'] - ticks['bid']
            med_sp = float(np.median(spreads))
            curr_sp = float(spreads[-1])
            spread_ratio = curr_sp / med_sp if med_sp > 0 else 1.0

        # Feature Vector Formulation
        features = np.array([gk_vol, ofi_delta, sweep_depth_pts, spread_ratio, atr], dtype=np.float32)

        # Calibrated Probability Curve
        # Base starts at 50% fair-value odds
        z = 0.0 + (1.65 * sweep_depth_pts) + (1.45 * ofi_delta if "LONG" in bias or "BULLISH" in bias else -1.45 * ofi_delta) - (0.50 * max(0.0, spread_ratio - 1.0))
        prob = 1.0 / (1.0 + math.exp(-z))

        return {
            "bias": bias,
            "probability": round(prob, 4),
            "features": features,
            "atr": float(atr),
            "spread_ratio": round(spread_ratio, 2),
            "ofi": round(ofi_delta, 2)
        }
"""

with open(r"C:\Quant-Nexus-Eng\apex_ml_feature_engine.py", "w", encoding="utf-8") as f:
    f.write(code)

print("✅ apex_ml_feature_engine.py successfully upgraded with live tick delta flow!")
