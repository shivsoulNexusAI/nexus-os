"""
SHIVSOUL 10K QUANT-NEXUS ECOSYSTEM
Dynamic Quarter-Kelly Position Sizing Engine
"""
from dataclasses import dataclass
from typing import Dict

@dataclass
class SymbolSpecs:
    symbol: str
    contract_size: float
    point_size: float
    tick_value_per_point: float  # Currency value of 1 point move per 1.0 lot
    min_lot: float = 0.01
    max_lot: float = 10.0
    lot_step: float = 0.01

# MT5 Standard Contract Registry
MARKET_REGISTRY: Dict[str, SymbolSpecs] = {
    "EURUSD": SymbolSpecs("EURUSD", 100000.0, 0.00001, 1.0),
    "GBPUSD": SymbolSpecs("GBPUSD", 100000.0, 0.00001, 1.0),
    "USDJPY": SymbolSpecs("USDJPY", 100000.0, 0.001,   0.65),
    "XAUUSD": SymbolSpecs("XAUUSD", 100.0,    0.01,    1.0),
    "BTCUSD": SymbolSpecs("BTCUSD", 1.0,      0.01,    1.0),
}

class KellyDynamicEngine:
    def __init__(
        self,
        kelly_fraction: float = 0.25,  # Defensive Quarter-Kelly
        min_risk_pct: float = 0.002,   # 0.2% floor
        max_risk_pct: float = 0.015    # 1.5% ceiling to respect circuit breaker
    ):
        self.k_frac = kelly_fraction
        self.min_risk = min_risk_pct
        self.max_risk = max_risk_pct

    def get_risk_fraction(self, win_rate: float = 0.55, payoff_ratio: float = 1.5) -> float:
        if payoff_ratio <= 0 or win_rate <= 0:
            return 0.0
        q = 1.0 - win_rate
        f_star = (payoff_ratio * win_rate - q) / payoff_ratio
        if f_star <= 0:
            return 0.0
        scaled_f = f_star * self.k_frac
        return max(self.min_risk, min(scaled_f, self.max_risk))

    def calculate_lot(
        self,
        symbol: str,
        sl_points: float,
        equity: float,
        win_rate: float = 0.55,
        payoff_ratio: float = 1.5
    ) -> float:
        spec = MARKET_REGISTRY.get(symbol)
        if not spec or equity <= 0 or sl_points <= 0:
            return 0.0

        risk_fraction = self.get_risk_fraction(win_rate, payoff_ratio)
        if risk_fraction <= 0:
            return 0.0

        dollar_risk = equity * risk_fraction
        risk_per_single_lot = sl_points * spec.tick_value_per_point

        if risk_per_single_lot <= 0:
            return 0.0

        raw_lot = dollar_risk / risk_per_single_lot
        steps = round(raw_lot / spec.lot_step)
        quantized = steps * spec.lot_step
        return max(spec.min_lot, min(round(quantized, 2), spec.max_lot))

if __name__ == "__main__":
    engine = KellyDynamicEngine(kelly_fraction=0.25)
    test_equity = 10000.0
    print(f"--- 10K Kelly Benchmark (Quarter-Kelly @ 55% WR, 1.5 R:R) ---")
    risk_pct = engine.get_risk_fraction(0.55, 1.5) * 100
    print(f"Target Risk Budget: {risk_pct:.2f}% (${test_equity * (risk_pct/100):.2f})")
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]:
        lots = engine.calculate_lot(sym, 250.0, test_equity)
        print(f"  {sym:<8} @ 250pts SL: {lots:.2f} Lots")
