import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

LOGIN = 278017866
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"

@dataclass
class FVG:
    symbol: str
    timeframe: int
    direction: str       # "BULLISH" or "BEARISH"
    top: float
    bottom: float
    candle_time: int
    mitigated: bool = False

@dataclass
class LiquiditySweep:
    symbol: str
    timeframe: int
    sweep_type: str     # "BUY_SIDE" or "SELL_SIDE"
    swept_level: float
    rejection_price: float
    candle_time: int

class ICTEngine:
    def __init__(self, fvg_min_points: float = 10.0, sweep_lookback: int = 20):
        self.fvg_min_points = fvg_min_points
        self.sweep_lookback = sweep_lookback

    def get_rates(self, symbol: str, timeframe: int, count: int = 100) -> Optional[pd.DataFrame]:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def scan_fvg(self, symbol: str, timeframe: int, count: int = 50) -> List[FVG]:
        df = self.get_rates(symbol, timeframe, count)
        if df is None or len(df) < 5:
            return []

        info = mt5.symbol_info(symbol)
        pt = info.point if info else 0.0001
        min_gap = self.fvg_min_points * pt

        fvgs = []
        for i in range(2, len(df) - 1):
            c1_high = df.loc[i - 2, 'high']
            c1_low  = df.loc[i - 2, 'low']
            c3_high = df.loc[i, 'high']
            c3_low  = df.loc[i, 'low']
            c_time  = int(df.loc[i - 1, 'time'].timestamp())

            if c3_low - c1_high >= min_gap:
                fvg = FVG(
                    symbol=symbol,
                    timeframe=timeframe,
                    direction="BULLISH",
                    top=c3_low,
                    bottom=c1_high,
                    candle_time=c_time
                )
                subsequent = df.iloc[i + 1:]
                if any(subsequent['low'] <= fvg.bottom):
                    fvg.mitigated = True
                fvgs.append(fvg)

            elif c1_low - c3_high >= min_gap:
                fvg = FVG(
                    symbol=symbol,
                    timeframe=timeframe,
                    direction="BEARISH",
                    top=c1_low,
                    bottom=c3_high,
                    candle_time=c_time
                )
                subsequent = df.iloc[i + 1:]
                if any(subsequent['high'] >= fvg.top):
                    fvg.mitigated = True
                fvgs.append(fvg)

        return fvgs

    def detect_liquidity_sweep(self, symbol: str, timeframe: int) -> Optional[LiquiditySweep]:
        df = self.get_rates(symbol, timeframe, self.sweep_lookback + 5)
        if df is None or len(df) < self.sweep_lookback + 2:
            return None

        prev_range = df.iloc[-(self.sweep_lookback + 2):-2]
        swing_high = prev_range['high'].max()
        swing_low  = prev_range['low'].min()

        closed_bar = df.iloc[-2]
        c_time = int(closed_bar['time'].timestamp())

        if closed_bar['high'] > swing_high and closed_bar['close'] < swing_high:
            return LiquiditySweep(
                symbol=symbol,
                timeframe=timeframe,
                sweep_type="BUY_SIDE",
                swept_level=swing_high,
                rejection_price=closed_bar['close'],
                candle_time=c_time
            )

        if closed_bar['low'] < swing_low and closed_bar['close'] > swing_low:
            return LiquiditySweep(
                symbol=symbol,
                timeframe=timeframe,
                sweep_type="SELL_SIDE",
                swept_level=swing_low,
                rejection_price=closed_bar['close'],
                candle_time=c_time
            )

        return None

    def evaluate_ict_confluence(self, symbol: str, timeframe: int = mt5.TIMEFRAME_M5) -> Dict[str, Any]:
        """
        Integrates liquidity sweeps and unmitigated Fair Value Gaps to determine
        the execution bias, edge boost, and ICT reason tags.
        """
        reasons = []
        edge_boost = 0.0
        bias = "FLAT"

        sweep = self.detect_liquidity_sweep(symbol, timeframe)
        if sweep:
            if sweep.sweep_type == "SELL_SIDE":
                bias = "BUY"
                edge_boost += 0.12
                reasons.append(f"SSL_SWEEP_{sweep.swept_level:.2f}")
            elif sweep.sweep_type == "BUY_SIDE":
                bias = "SELL"
                edge_boost += 0.12
                reasons.append(f"BSL_SWEEP_{sweep.swept_level:.2f}")

        fvgs = self.scan_fvg(symbol, timeframe, count=35)
        unmitigated = [f for f in fvgs if not f.mitigated]

        if unmitigated:
            latest_fvg = unmitigated[-1]
            if latest_fvg.direction == "BULLISH":
                if bias == "BUY":
                    edge_boost += 0.08
                elif bias == "FLAT":
                    bias = "BUY"
                    edge_boost += 0.05
                reasons.append(f"BULL_FVG_[{latest_fvg.bottom:.2f}-{latest_fvg.top:.2f}]")
            elif latest_fvg.direction == "BEARISH":
                if bias == "SELL":
                    edge_boost += 0.08
                elif bias == "FLAT":
                    bias = "SELL"
                    edge_boost += 0.05
                reasons.append(f"BEAR_FVG_[{latest_fvg.top:.2f}-{latest_fvg.bottom:.2f}]")

        return {
            "bias": bias,
            "edge_boost": round(min(0.25, edge_boost), 2),
            "reasons": reasons
        }

def main():
    if not mt5.initialize() or not mt5.login(login=LOGIN, password=PASSWORD, server=SERVER):
        print("MT5 Connection Failed")
        return

    engine = ICTEngine(fvg_min_points=10.0, sweep_lookback=20)
    for sym in ["XAUUSD", "BTCUSD", "USDJPY"]:
        conf = engine.evaluate_ict_confluence(sym, mt5.TIMEFRAME_M5)
        print(f"[{sym}] Bias: {conf['bias']} | Boost: +{conf['edge_boost']} | Reasons: {conf['reasons']}")
    mt5.shutdown()

if __name__ == "__main__":
    main()
