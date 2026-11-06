r"""
QuantNexus Production - Gold/Silver Ratio (GSR) & Z-Score Telemetry Engine
Location: C:\Quant-Nexus-Prod\core\gsr_engine.py
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

@dataclass
class GSRMetrics:
    timestamp: str
    gold_symbol: str
    silver_symbol: str
    gold_price: float
    silver_price: float
    current_gsr: float
    rolling_mean_gsr: float
    rolling_std_gsr: float
    gsr_zscore: float
    regime: str             # "EXTREME_HIGH_RATIO", "EXTREME_LOW_RATIO", "NORMAL_EQUILIBRIUM"
    divergence_edge: str    # "FAVOR_SILVER_LONG", "FAVOR_GOLD_LONG", "NEUTRAL"

class GSREngine:
    def __init__(self, lookback: int = 50, z_threshold: float = 2.0):
        self.lookback = lookback
        self.z_threshold = z_threshold
        self.gold_symbol = self._resolve_symbol(["XAUUSD", "GOLD"])
        self.silver_symbol = self._resolve_symbol(["XAGUSD", "SILVER"])

    def _resolve_symbol(self, candidates: list) -> str:
        for sym in candidates:
            info = mt5.symbol_info(sym)
            if info is not None:
                if not info.visible:
                    mt5.symbol_select(sym, True)
                rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 5)
                if rates is not None and len(rates) > 0:
                    return sym
        return candidates[0]

    def compute_metrics(self) -> Optional[GSRMetrics]:
        r_au = mt5.copy_rates_from_pos(self.gold_symbol, mt5.TIMEFRAME_M5, 0, self.lookback)
        r_ag = mt5.copy_rates_from_pos(self.silver_symbol, mt5.TIMEFRAME_M5, 0, self.lookback)

        if r_au is None or r_ag is None or len(r_au) < 20 or len(r_ag) < 20:
            return None

        df_au = pd.DataFrame(r_au)[["time", "close"]].rename(columns={"close": "gold_close"})
        df_ag = pd.DataFrame(r_ag)[["time", "close"]].rename(columns={"close": "silver_close"})

        merged = pd.merge(df_au, df_ag, on="time").dropna()
        if len(merged) < 20:
            return None

        merged["gsr"] = merged["gold_close"] / merged["silver_close"]
        
        current_gsr = float(merged["gsr"].iloc[-1])
        mean_gsr = float(merged["gsr"].mean())
        std_gsr = float(merged["gsr"].std())

        if std_gsr == 0:
            z_score = 0.0
        else:
            z_score = float((current_gsr - mean_gsr) / std_gsr)

        # Classify regime & tactical bias
        if z_score >= self.z_threshold:
            regime = "EXTREME_HIGH_RATIO"
            edge = "FAVOR_SILVER_LONG"     # Silver historically underpriced relative to Gold
        elif z_score <= -self.z_threshold:
            regime = "EXTREME_LOW_RATIO"
            edge = "FAVOR_GOLD_LONG"       # Gold historically underpriced relative to Silver
        else:
            regime = "NORMAL_EQUILIBRIUM"
            edge = "NEUTRAL"

        last_time = pd.to_datetime(merged["time"].iloc[-1], unit="s").isoformat()

        return GSRMetrics(
            timestamp=last_time,
            gold_symbol=self.gold_symbol,
            silver_symbol=self.silver_symbol,
            gold_price=round(float(merged["gold_close"].iloc[-1]), 3),
            silver_price=round(float(merged["silver_close"].iloc[-1]), 3),
            current_gsr=round(current_gsr, 2),
            rolling_mean_gsr=round(mean_gsr, 2),
            rolling_std_gsr=round(std_gsr, 3),
            gsr_zscore=round(z_score, 2),
            regime=regime,
            divergence_edge=edge
        )

# Standalone verification
if __name__ == "__main__":
    if not mt5.initialize():
        print("[-] MT5 initialization failed.")
        sys.exit(1)
    
    engine = GSREngine()
    res = engine.compute_metrics()
    if res:
        print("================ GSR & Z-SCORE ENGINE DIAGNOSTIC ================")
        print(f"Timestamp        : {res.timestamp}")
        print(f"Gold Price       : ${res.gold_price} ({res.gold_symbol})")
        print(f"Silver Price     : ${res.silver_price} ({res.silver_symbol})")
        print(f"Current GSR      : {res.current_gsr}")
        print(f"Rolling Mean (N) : {res.rolling_mean_gsr} (σ = {res.rolling_std_gsr})")
        print(f"GSR Z-Score      : {res.gsr_zscore} σ")
        print(f"Regime           : {res.regime}")
        print(f"Tactical Edge    : {res.divergence_edge}")
        print("=================================================================")
    else:
        print("[-] Insufficient rate history to compute GSR metrics.")
    mt5.shutdown()
