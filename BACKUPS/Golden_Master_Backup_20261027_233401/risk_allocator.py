"""
SHIVSOUL SOVEREIGN NEXUS // DYNAMIC FRACTIONAL KELLY RISK ENGINE
Calculates precision lot sizing based on historical win/loss ratios, 
Kronos edge scores, and live MT5 account equity.
"""
import os
import sys
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

class DynamicKellyAllocator:
    def __init__(
        self,
        default_win_rate: float = 0.58,
        default_payoff_ratio: float = 2.0,  # 1:2 R:R baseline
        kelly_fraction: float = 0.25,       # Quarter-Kelly safety cushion
        min_risk_pct: float = 0.005,        # 0.5% minimum floor
        max_risk_pct: float = 0.020         # 2.0% maximum risk ceiling
    ):
        self.default_p = default_win_rate
        self.default_b = default_payoff_ratio
        self.fraction = kelly_fraction
        self.min_risk = min_risk_pct
        self.max_risk = max_risk_pct

    def compute_empirical_stats(self, lookback_days: int = 30) -> Dict[str, float]:
        """Queries MT5 closed trade history to compute rolling empirical P and B."""
        if not HAS_MT5 or not mt5.initialize():
            return {"win_rate": self.default_p, "payoff_ratio": self.default_b, "sample_size": 0}

        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)
        
        deals = mt5.history_deals_get(start, now)
        if not deals:
            return {"win_rate": self.default_p, "payoff_ratio": self.default_b, "sample_size": 0}

        profits = [d.profit for d in deals if d.entry == 1 and d.profit != 0] # Exit deals
        if len(profits) < 10:
            return {"win_rate": self.default_p, "payoff_ratio": self.default_b, "sample_size": len(profits)}

        wins = [p for p in profits if p > 0]
        losses = [abs(p) for p in profits if p < 0]

        win_rate = len(wins) / len(profits) if profits else self.default_p
        avg_win = np.mean(wins) if wins else 1.0
        avg_loss = np.mean(losses) if losses else 1.0
        payoff_ratio = float(avg_win / avg_loss) if avg_loss > 0 else self.default_b

        return {
            "win_rate": float(np.clip(win_rate, 0.35, 0.85)),
            "payoff_ratio": float(np.clip(payoff_ratio, 1.0, 4.0)),
            "sample_size": len(profits)
        }

    def calculate_lot_size(
        self,
        symbol: str,
        entry_price: float,
        sl_price: float,
        edge_score: float = 0.85
    ) -> Dict[str, Any]:
        """Derives exact institutional lot size and equity commitment."""
        if not HAS_MT5 or not mt5.initialize():
            return {"lots": 0.01, "risk_amount": 0.0, "risk_pct": 0.005, "status": "MT5_OFFLINE"}

        account = mt5.account_info()
        sym_info = mt5.symbol_info(symbol)
        if not account or not sym_info:
            return {"lots": 0.01, "risk_amount": 0.0, "risk_pct": 0.005, "status": "INFO_ERROR"}

        equity = account.equity
        stats = self.compute_empirical_stats()
        p = stats["win_rate"]
        b = stats["payoff_ratio"]

        # 1. Full Kelly: f* = p - (1 - p) / b
        full_kelly = p - ((1.0 - p) / b)
        if full_kelly <= 0:
            raw_risk = self.min_risk
        else:
            # 2. Scale by Quarter-Kelly and Kronos Edge conviction
            edge_scalar = edge_score / 0.80  # Base benchmark is 80% edge
            raw_risk = full_kelly * self.fraction * edge_scalar

        # 3. Apply risk boundaries
        risk_pct = float(np.clip(raw_risk, self.min_risk, self.max_risk))
        risk_amount = equity * risk_pct

        # 4. Pip / Point calculation
        sl_dist = abs(entry_price - sl_price)
        if sl_dist <= 0:
            sl_dist = 10 * sym_info.point * 10

        # Contract sizing formula
        # Value per point per 1.0 lot
        point_val = sym_info.trade_tick_value
        point_size = sym_info.trade_tick_size
        if point_size <= 0:
            point_size = sym_info.point

        cost_per_lot_move = (sl_dist / point_size) * point_val

        if cost_per_lot_move <= 0:
            raw_lots = sym_info.volume_min
        else:
            raw_lots = risk_amount / cost_per_lot_move

        # Round to volume step
        step = sym_info.volume_step if sym_info.volume_step > 0 else 0.01
        lots = round(raw_lots / step) * step
        lots = float(np.clip(lots, sym_info.volume_min, sym_info.volume_max))

        return {
            "lots": round(lots, 2),
            "risk_amount_usd": round(risk_amount, 2),
            "risk_pct": round(risk_pct * 100, 2),
            "full_kelly": round(full_kelly * 100, 2),
            "quarter_kelly": round(raw_risk * 100, 2),
            "empirical_win_rate": round(p * 100, 1),
            "empirical_payoff": round(b, 2),
            "equity": round(equity, 2),
            "status": "CALCULATED"
        }

kelly_engine = DynamicKellyAllocator()
