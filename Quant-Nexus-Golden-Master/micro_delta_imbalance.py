"""
Quant Nexus: Elite Omega Engine
Module: micro_delta_imbalance.py
Description: Evaluates real-time tick-level order book imbalance and CVD
             to filter out false breakouts and confirm institutional participation.
"""

from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
import numpy as np


class MicroDeltaImbalance:
    def __init__(self, tick_lookback: int = 500, imbalance_threshold: float = 0.25):
        """
        :param tick_lookback: Number of raw ticks to ingest for order flow profiling
        :param imbalance_threshold: Required minimum normalized delta imbalance (-1.0 to +1.0)
        """
        self.tick_lookback = tick_lookback
        self.imbalance_threshold = imbalance_threshold

    def compute_order_flow_metrics(self, symbol: str) -> dict:
        """
        Fetches tick array and computes Cumulative Volume Delta (CVD) and Imbalance Ratio (DIR).
        """
        utc_from = datetime.utcnow() - timedelta(minutes=30)
        ticks = mt5.copy_ticks_from(symbol, utc_from, self.tick_lookback, mt5.COPY_TICKS_ALL)

        if ticks is None or len(ticks) < 50:
            return {
                "symbol": symbol,
                "status": "INSUFFICIENT_DATA",
                "cvd": 0.0,
                "dir": 0.0,
                "valid": False,
            }

        df = pd.DataFrame(ticks)
        
        if "volume" not in df.columns or df["volume"].sum() == 0:
            df["volume"] = 1.0

        price_diff = df["bid"].diff().fillna(0)
        
        buy_mask = (df["flags"] & mt5.TICK_FLAG_BUY) > 0
        sell_mask = (df["flags"] & mt5.TICK_FLAG_SELL) > 0

        if not buy_mask.any() and not sell_mask.any():
            buy_mask = price_diff > 0
            sell_mask = price_diff < 0

        buy_vol = np.where(buy_mask, df["volume"], 0.0).sum()
        sell_vol = np.where(sell_mask, df["volume"], 0.0).sum()
        total_vol = buy_vol + sell_vol

        if total_vol == 0:
            dir_ratio = 0.0
        else:
            dir_ratio = float((buy_vol - sell_vol) / total_vol)

        cvd = float(buy_vol - sell_vol)

        return {
            "symbol": symbol,
            "status": "OPTIMAL",
            "buy_volume": float(buy_vol),
            "sell_volume": float(sell_vol),
            "total_volume": float(total_vol),
            "cvd": cvd,
            "dir": round(dir_ratio, 4),
            "valid": True
        }

    def validate_setup(self, symbol: str, direction: str) -> tuple[bool, str]:
        """
        Validates whether raw tick order flow corroborates the directional scan.
        """
        metrics = self.compute_order_flow_metrics(symbol)
        
        if not metrics["valid"]:
            return False, f"Delta check rejected: {metrics['status']}"

        dir_score = metrics["dir"]

        if direction.upper() == "BUY":
            if dir_score >= self.imbalance_threshold:
                return True, f"Confirmed Bullish Delta: DIR={dir_score:+.2%} | CVD={metrics['cvd']:.0f}"
            else:
                return False, f"Divergence Warning: BUY setup lacks aggressive buying (DIR={dir_score:+.2%})"

        elif direction.upper() == "SELL":
            if dir_score <= -self.imbalance_threshold:
                return True, f"Confirmed Bearish Delta: DIR={dir_score:+.2%} | CVD={metrics['cvd']:.0f}"
            else:
                return False, f"Divergence Warning: SELL setup lacks aggressive selling (DIR={dir_score:+.2%})"

        return False, f"Invalid direction parameter: {direction}"