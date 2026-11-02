import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from typing import Dict, Optional

class VolatilityParityAllocator:
    def __init__(self, target_risk_pct: float = 0.01, atr_period: int = 14):
        self.target_risk_pct = target_risk_pct
        self.atr_period = atr_period

    def calculate_atr(self, symbol: str, timeframe: int = mt5.TIMEFRAME_H1) -> float:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, self.atr_period + 5)
        if rates is None or len(rates) < self.atr_period + 1:
            return 0.0

        df = pd.DataFrame(rates)
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1)

        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.tail(self.atr_period).mean()
        return float(atr)

    def get_symbol_lot_limits(self, symbol: str) -> Dict[str, float]:
        info = mt5.symbol_info(symbol)
        if not info:
            return {"min": 0.01, "max": 10.0, "step": 0.01, "contract": 1.0, "tick_val": 1.0, "tick_size": 0.01}

        return {
            "min": info.volume_min,
            "max": info.volume_max,
            "step": info.volume_step,
            "contract": info.trade_contract_size,
            "tick_val": info.trade_tick_value if info.trade_tick_value else 1.0,
            "tick_size": info.trade_tick_size if info.trade_tick_size else 0.01
        }

    def compute_parity_lot_size(self, symbol: str, equity: float, timeframe: int = mt5.TIMEFRAME_H1) -> float:
        atr = self.calculate_atr(symbol, timeframe)
        if atr <= 0.0:
            return 0.01

        limits = self.get_symbol_lot_limits(symbol)
        cash_risk_budget = equity * self.target_risk_pct

        if limits["tick_size"] > 0 and limits["tick_val"] > 0:
            dollar_risk_per_lot = (atr / limits["tick_size"]) * limits["tick_val"]
        else:
            dollar_risk_per_lot = atr * limits["contract"]

        if dollar_risk_per_lot <= 0.0:
            return limits["min"]

        raw_lot = cash_risk_budget / dollar_risk_per_lot
        step = limits["step"]
        normalized_lot = np.floor(raw_lot / step) * step
        final_lot = max(limits["min"], min(limits["max"], normalized_lot))
        return round(float(final_lot), 2)


class QuarterKellyAllocator:
    def __init__(self, default_win_rate: float = 0.55, default_rr: float = 1.5):
        self.default_win_rate = default_win_rate
        self.default_rr = default_rr
        self.parity_allocator = VolatilityParityAllocator()

    def calculate_lot_size(self, symbol: str, equity: float, win_rate: Optional[float] = None, rr_ratio: Optional[float] = None) -> float:
        p = win_rate if win_rate is not None else self.default_win_rate
        b = rr_ratio if rr_ratio is not None else self.default_rr
        q = 1.0 - p

        full_kelly = (b * p - q) / b if b > 0 else 0.0
        quarter_kelly = max(0.005, min(0.025, 0.25 * full_kelly)) if full_kelly > 0 else 0.01

        base_allocator = VolatilityParityAllocator(target_risk_pct=quarter_kelly)
        return base_allocator.compute_parity_lot_size(symbol, equity)

    def __call__(self, *args, **kwargs):
        if len(args) >= 2:
            return self.calculate_lot_size(symbol=args[0], equity=args[1])
        return self.calculate_lot_size(**kwargs)

kelly_allocator = QuarterKellyAllocator()

def calculate_kelly_size(symbol: str, equity: float, win_rate: float = 0.55, rr_ratio: float = 1.5) -> float:
    return kelly_allocator.calculate_lot_size(symbol, equity, win_rate, rr_ratio)
