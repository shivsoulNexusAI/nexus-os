r"""
QuantNexus Production - Omega Apex Elite Vision: DXY & XAUUSD Correlation Engine
Location: C:\Quant-Nexus-Prod\core\dxy_gold_correlation_vision.py
"""

import sys
import time
from dataclasses import dataclass
from typing import Optional, Tuple
import pandas as pd
import MetaTrader5 as mt5

@dataclass
class CorrelationState:
    gold_symbol: str
    dxy_symbol: str
    pearson_corr: float
    regime: str                     # "INVERSE_NORMAL", "DECOUPLED_RISK_OFF", "TRANSITIONAL"
    smt_divergence: Optional[str]   # "BULLISH_SMT", "BEARISH_SMT", None
    dxy_bias: str                   # "BULLISH", "BEARISH", "NEUTRAL"
    gold_signal_multiplier: float   # Edge modifier (0.50x to 1.35x)
    trade_bias: str                 # "BUY", "SELL", "HOLD"
    confidence_score: float

class ApexDXYGoldVision:
    def __init__(self, gold_symbol: str = "XAUUSD", lookback_bars: int = 40):
        self.gold_symbol = gold_symbol
        self.lookback = lookback_bars
        self.dxy_symbol = self._resolve_dxy_symbol()

    def _resolve_dxy_symbol(self) -> str:
        """Finds active broker DXY ticker with valid candle history or falls back to inverted EURUSD."""
        # DXY confirmed active on MT5 broker terminal
        candidates = ["DXY", "USDX", "DX", "USDINDEX", "DXY.c", "USDX.c"]
        for sym in candidates:
            info = mt5.symbol_info(sym)
            if info is not None:
                if not info.visible:
                    mt5.symbol_select(sym, True)
                # Verify that terminal actually serves bar history for this symbol
                test_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 5)
                if test_rates is not None and len(test_rates) > 0:
                    return sym

        # Robust synthetic anchor if no direct dollar index bar history is returned
        if mt5.symbol_info("EURUSD") is not None:
            if not mt5.symbol_info("EURUSD").visible:
                mt5.symbol_select("EURUSD", True)
            return "EURUSD_INVERTED"
            
        return "DXY"

    def fetch_rates(self, symbol: str, timeframe=mt5.TIMEFRAME_M5) -> pd.DataFrame:
        actual_sym = "EURUSD" if symbol == "EURUSD_INVERTED" else symbol
        
        # Ensure symbol is active in Market Watch
        info = mt5.symbol_info(actual_sym)
        if info and not info.visible:
            mt5.symbol_select(actual_sym, True)

        rates = mt5.copy_rates_from_pos(actual_sym, timeframe, 0, self.lookback)
        if rates is None or len(rates) == 0:
            # Short wait for terminal to sync candle database on first cold query
            time.sleep(0.2)
            rates = mt5.copy_rates_from_pos(actual_sym, timeframe, 0, self.lookback)

        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            raise ValueError(f"Failed to copy rates for {actual_sym} from MT5. Error: {err}")
            
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        
        # Invert EURUSD to replicate Dollar Index action if proxy is used
        if symbol == "EURUSD_INVERTED":
            df["close"] = 1.0 / df["close"]
            high_inv = 1.0 / df["low"]
            low_inv = 1.0 / df["high"]
            df["high"] = high_inv
            df["low"] = low_inv
            
        return df

    def compute_regime(self, gold_df: pd.DataFrame, dxy_df: pd.DataFrame) -> Tuple[float, str]:
        merged = pd.merge(
            gold_df[["time", "close"]],
            dxy_df[["time", "close"]],
            on="time",
            suffixes=("_gold", "_dxy")
        )
        if len(merged) < 15:
            return 0.0, "TRANSITIONAL"

        corr = merged["close_gold"].corr(merged["close_dxy"])

        if corr <= -0.65:
            regime = "INVERSE_NORMAL"
        elif corr >= -0.15:
            regime = "DECOUPLED_RISK_OFF"
        else:
            regime = "TRANSITIONAL"

        return float(corr), regime

    def detect_smt(self, gold_df: pd.DataFrame, dxy_df: pd.DataFrame) -> Optional[str]:
        gold_high_1 = gold_df["high"].iloc[-20:-10].max()
        gold_high_2 = gold_df["high"].iloc[-10:].max()
        gold_low_1 = gold_df["low"].iloc[-20:-10].min()
        gold_low_2 = gold_df["low"].iloc[-10:].min()

        dxy_high_1 = dxy_df["high"].iloc[-20:-10].max()
        dxy_high_2 = dxy_df["high"].iloc[-10:].max()
        dxy_low_1 = dxy_df["low"].iloc[-20:-10].min()
        dxy_low_2 = dxy_df["low"].iloc[-10:].min()

        # Bearish SMT: DXY makes Lower Low, Gold fails to make Higher High
        if (dxy_low_2 < dxy_low_1) and (gold_high_2 <= gold_high_1):
            return "BEARISH_SMT"

        # Bullish SMT: DXY makes Higher High, Gold fails to make Lower Low
        if (dxy_high_2 > dxy_high_1) and (gold_low_2 >= gold_low_1):
            return "BULLISH_SMT"

        return None

    def evaluate_vision(self) -> CorrelationState:
        # Re-resolve in case MT5 connection state re-anchored
        if not hasattr(self, "dxy_symbol") or not self.dxy_symbol:
            self.dxy_symbol = self._resolve_dxy_symbol()

        gold_df = self.fetch_rates(self.gold_symbol)
        dxy_df = self.fetch_rates(self.dxy_symbol)

        corr, regime = self.compute_regime(gold_df, dxy_df)
        smt = self.detect_smt(gold_df, dxy_df)

        dxy_ema_fast = dxy_df["close"].ewm(span=9).mean().iloc[-1]
        dxy_ema_slow = dxy_df["close"].ewm(span=21).mean().iloc[-1]
        dxy_bias = "BULLISH" if dxy_ema_fast > dxy_ema_slow else "BEARISH"

        trade_bias = "HOLD"
        multiplier = 1.0
        confidence = 0.50

        if regime == "INVERSE_NORMAL":
            if smt == "BEARISH_SMT" and dxy_bias == "BULLISH":
                trade_bias = "SELL"
                multiplier = 1.35
                confidence = 0.90
            elif smt == "BULLISH_SMT" and dxy_bias == "BEARISH":
                trade_bias = "BUY"
                multiplier = 1.35
                confidence = 0.90
            elif dxy_bias == "BULLISH":
                trade_bias = "SELL"
                confidence = 0.75
            elif dxy_bias == "BEARISH":
                trade_bias = "BUY"
                confidence = 0.75
        elif regime == "DECOUPLED_RISK_OFF":
            multiplier = 0.50
            confidence = 0.40
            trade_bias = "HOLD"

        return CorrelationState(
            gold_symbol=self.gold_symbol,
            dxy_symbol=self.dxy_symbol,
            pearson_corr=round(corr, 3),
            regime=regime,
            smt_divergence=smt,
            dxy_bias=dxy_bias,
            gold_signal_multiplier=multiplier,
            trade_bias=trade_bias,
            confidence_score=confidence
        )

if __name__ == "__main__":
    if not mt5.initialize():
        print("[-] MT5 initialization failed.")
        sys.exit(1)

    try:
        engine = ApexDXYGoldVision()
        state = engine.evaluate_vision()

        print("=" * 65)
        print("     OMEGA APEX ELITE: DXY vs. XAUUSD CORRELATION VISION     ")
        print("=" * 65)
        print(f"Target Gold Symbol        : {state.gold_symbol}")
        print(f"Resolved DXY Anchor       : {state.dxy_symbol}")
        print(f"Rolling Pearson Corr (M5) : {state.pearson_corr}")
        print(f"Macro Correlation Regime  : {state.regime}")
        print(f"Detected SMT Divergence   : {state.smt_divergence}")
        print(f"Dollar Index Bias         : {state.dxy_bias}")
        print(f"Recommended Gold Action   : {state.trade_bias}")
        print(f"Position Sizing Mod       : {state.gold_signal_multiplier}x")
        print(f"Confidence Score          : {state.confidence_score * 100:.1f}%")
        print("=" * 65)
    except Exception as e:
        print(f"[-] Error executing correlation test: {e}")
    finally:
        mt5.shutdown()
