from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

@dataclass
class SizingResult:
    symbol: str
    direction: str
    target_risk_usd: float
    raw_lots: float
    clamped_lots: float
    atr_points: float
    point_cost_usd: float
    is_allowed: bool
    throttle_reason: str

class CrossAssetRiskGovernor:
    def __init__(self, max_portfolio_risk_pct: float = 0.04, single_trade_risk_pct: float = 0.01, max_cluster_correlation: float = 0.70, correlation_lookback_bars: int = 40, max_symbol_lot_cap: float = 0.05):
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.single_trade_risk_pct = single_trade_risk_pct
        self.max_cluster_correlation = max_cluster_correlation
        self.correlation_lookback_bars = correlation_lookback_bars
        self.max_lot_cap = max_symbol_lot_cap

    def fetch_log_returns(self, symbol: str, timeframe=mt5.TIMEFRAME_H1) -> Optional[pd.Series]:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, self.correlation_lookback_bars + 1)
        if rates is None or len(rates) < self.correlation_lookback_bars: return None
        closes = pd.Series([r['close'] for r in rates])
        return np.log(closes / closes.shift(1)).dropna()

    def evaluate_correlation_throttle(self, candidate_symbol: str, candidate_direction: str) -> Tuple[bool, str, float]:
        positions = mt5.positions_get()
        if not positions:
            return True, "No active positions", 0.0

        c_ret = self.fetch_log_returns(candidate_symbol)
        if c_ret is None:
            return True, "Pass without throttle (no returns)", 0.0

        for p in positions:
            if p.symbol == candidate_symbol:
                return False, f"Lockout: Position open on {candidate_symbol}", 1.0
            p_dir = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
            p_ret = self.fetch_log_returns(p.symbol)
            if p_ret is None: continue
            df = pd.DataFrame({"p": p_ret, "c": c_ret}).dropna()
            if len(df) < 20: continue
            corr = float(df["p"].corr(df["c"]))
            same = (p_dir == candidate_direction)
            if (same and corr >= self.max_cluster_correlation) or (not same and corr <= -self.max_cluster_correlation):
                return False, f"VETO: Correlation with {p.symbol} ({corr:.2f}) exceeds +/-{self.max_cluster_correlation:.2f}", corr

        return True, "Correlation clear", 0.0
