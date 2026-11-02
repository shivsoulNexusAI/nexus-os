"""
SHIVSOUL SOVEREIGN NEXUS // MULTI-TIMEFRAME MACRO ENGINE (mtf_engine.py)
Extracts structural trend bias and moving average ribbons across H1 and H4.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

class MTFEngine:
    def __init__(self):
        self.tf_map = {
            "M15": mt5.TIMEFRAME_M15 if HAS_MT5 else 15,
            "H1":  mt5.TIMEFRAME_H1 if HAS_MT5 else 60,
            "H4":  mt5.TIMEFRAME_H4 if HAS_MT5 else 240
        }

    def fetch_bars(self, symbol: str, timeframe_str: str, count: int = 60) -> Optional[pd.DataFrame]:
        if not HAS_MT5 or not mt5.initialize():
            return None
        tf = self.tf_map.get(timeframe_str)
        if tf is None:
            return None
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        return df

    def evaluate_trend_bias(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculates ribbon geometry (EMA 20, 50, 200) and market structure."""
        closes = df['close'].to_numpy()
        if len(closes) < 50:
            return {"bias": "NEUTRAL", "strength": 0.50, "ema20": closes[-1], "ema50": closes[-1]}

        ema20 = pd.Series(closes).ewm(span=20).mean().iloc[-1]
        ema50 = pd.Series(closes).ewm(span=50).mean().iloc[-1]
        
        # 200 EMA check if sufficient depth
        if len(closes) >= 100:
            ema200 = pd.Series(closes).ewm(span=100).mean().iloc[-1]
        else:
            ema200 = ema50

        last_close = closes[-1]
        
        # Bullish alignment: Price > EMA20 > EMA50
        if last_close > ema20 and ema20 > ema50:
            bias = "BULLISH"
            strength = 0.90 if last_close > ema200 else 0.70
        # Bearish alignment: Price < EMA20 < EMA50
        elif last_close < ema20 and ema20 < ema50:
            bias = "BEARISH"
            strength = 0.90 if last_close < ema200 else 0.70
        else:
            bias = "CONSOLIDATION"
            strength = 0.50

        return {
            "bias": bias,
            "strength": strength,
            "ema20": float(ema20),
            "ema50": float(ema50),
            "close": float(last_close)
        }

    def get_macro_structure(self, symbol: str) -> Dict[str, Any]:
        """Scans H1 and H4 horizons and outputs higher-timeframe consensus."""
        df_h1 = self.fetch_bars(symbol, "H1", count=70)
        df_h4 = self.fetch_bars(symbol, "H4", count=70)

        h1_eval = self.evaluate_trend_bias(df_h1) if df_h1 is not None else {"bias": "NEUTRAL", "strength": 0.5}
        h4_eval = self.evaluate_trend_bias(df_h4) if df_h4 is not None else {"bias": "NEUTRAL", "strength": 0.5}

        return {
            "H1": h1_eval,
            "H4": h4_eval
        }

mtf_engine = MTFEngine()
