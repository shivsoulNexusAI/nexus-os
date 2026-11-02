from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import numpy as np
import MetaTrader5 as mt5

@dataclass
class MacroState:
    synthetic_dxy: float
    dxy_velocity_h1: float
    dxy_trend: str
    roro_score: float
    roro_regime: str
    basket_readings: Dict[str, float]
    usd_veto_long: bool
    usd_veto_short: bool

class MacroRegimeEngine:
    DXY_WEIGHTS = {"EURUSD": -0.601, "USDJPY": 0.142, "GBPUSD": -0.124, "USDCAD": 0.095, "USDCHF": 0.038}
    DXY_BASE_SCALE = 50.14348112

    def __init__(self, lookback_bars: int = 48, dxy_velocity_threshold: float = 0.0015, roro_threshold: float = 0.35):
        self.lookback_bars = lookback_bars
        self.dxy_velocity_threshold = dxy_velocity_threshold
        self.roro_threshold = roro_threshold

    def _get_price(self, symbol: str) -> Optional[float]:
        tick = mt5.symbol_info_tick(symbol)
        return (tick.bid + tick.ask) / 2.0 if tick and tick.bid > 0 and tick.ask > 0 else None

    def calculate_synthetic_dxy(self) -> Tuple[float, float, str]:
        product = 1.0
        for sym, weight in self.DXY_WEIGHTS.items():
            mt5.symbol_select(sym, True)
            p = self._get_price(sym)
            if not p: return 0.0, 0.0, "UNAVAILABLE"
            product *= (p ** weight)
        dxy = self.DXY_BASE_SCALE * product

        eur = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 2)
        jpy = mt5.copy_rates_from_pos("USDJPY", mt5.TIMEFRAME_H1, 0, 2)
        gbp = mt5.copy_rates_from_pos("GBPUSD", mt5.TIMEFRAME_H1, 0, 2)
        cad = mt5.copy_rates_from_pos("USDCAD", mt5.TIMEFRAME_H1, 0, 2)
        chf = mt5.copy_rates_from_pos("USDCHF", mt5.TIMEFRAME_H1, 0, 2)
        if any(r is None or len(r) < 2 for r in [eur, jpy, gbp, cad, chf]):
            return round(dxy, 3), 0.0, "NEUTRAL"

        prev_prod = ((eur[0]['close']**-0.601) * (jpy[0]['close']**0.142) * (gbp[0]['close']**-0.124) * (cad[0]['close']**0.095) * (chf[0]['close']**0.038))
        prev_dxy = self.DXY_BASE_SCALE * prev_prod
        vel = (dxy - prev_dxy) / prev_dxy
        trend = "EXPANSION" if vel > self.dxy_velocity_threshold else "COMPRESSION" if vel < -self.dxy_velocity_threshold else "NEUTRAL"
        return round(dxy, 3), round(vel, 5), trend

    def calculate_roro_score(self) -> Tuple[float, str, Dict[str, float]]:
        readings, on_rets, off_rets = {}, [], []
        for s in ["AUDUSD", "NZDUSD", "BTCUSD"]:
            mt5.symbol_select(s, True)
            r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_H1, 0, self.lookback_bars)
            if r is not None and len(r) >= self.lookback_bars:
                ret = (r[-1]['close'] - r[0]['close']) / r[0]['close']
                readings[s] = round(ret * 100, 2)
                on_rets.append(ret)

        for s in ["USDCHF", "USDJPY", "XAUUSD"]:
            mt5.symbol_select(s, True)
            r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_H1, 0, self.lookback_bars)
            if r is not None and len(r) >= self.lookback_bars:
                ret = (r[-1]['close'] - r[0]['close']) / r[0]['close']
                readings[s] = round(ret * 100, 2)
                off_rets.append(ret)

        if not on_rets or not off_rets:
            return 0.0, "BALANCED", readings

        spread = (np.mean(on_rets) - np.mean(off_rets)) * 25.0
        score = float(np.tanh(spread))
        regime = "RISK_ON" if score >= self.roro_threshold else "RISK_OFF" if score <= -self.roro_threshold else "BALANCED"
        return round(score, 3), regime, readings

    def evaluate_macro_state(self) -> MacroState:
        dxy, vel, trend = self.calculate_synthetic_dxy()
        roro, reg, readings = self.calculate_roro_score()
        return MacroState(
            synthetic_dxy=dxy, dxy_velocity_h1=vel, dxy_trend=trend,
            roro_score=roro, roro_regime=reg, basket_readings=readings,
            usd_veto_long=(trend == "EXPANSION" and vel > 0.0025),
            usd_veto_short=(trend == "COMPRESSION" and vel < -0.0025)
        )
