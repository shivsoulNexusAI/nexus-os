import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from typing import Dict, List, Optional, Tuple

class CorrelationMatrixGate:
    def __init__(self, lookback_bars: int = 50, correlation_threshold: float = 0.70):
        """
        :param lookback_bars: Number of M15/H1 bars to estimate rolling covariance.
        :param correlation_threshold: Correlation hurdle (rho > 0.70) to trigger risk lockout.
        """
        self.lookback_bars = lookback_bars
        self.correlation_threshold = correlation_threshold

    def get_returns(self, symbol: str, timeframe: int = mt5.TIMEFRAME_M15) -> Optional[pd.Series]:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, self.lookback_bars + 1)
        if rates is None or len(rates) < self.lookback_bars:
            return None
        closes = pd.Series([r['close'] for r in rates])
        returns = np.log(closes / closes.shift(1)).dropna()
        return returns

    def compute_matrix(self, symbols: List[str], timeframe: int = mt5.TIMEFRAME_M15) -> pd.DataFrame:
        returns_dict = {}
        for s in symbols:
            ret = self.get_returns(s, timeframe)
            if ret is not None:
                returns_dict[s] = ret
        
        df = pd.DataFrame(returns_dict)
        if df.empty or len(df.columns) < 2:
            return pd.DataFrame()
        return df.corr(method="pearson")

    def evaluate_order_risk(
        self,
        candidate_symbol: str,
        candidate_type: int,  # mt5.ORDER_TYPE_BUY or mt5.ORDER_TYPE_SELL
        active_positions: List,
        timeframe: int = mt5.TIMEFRAME_M15
    ) -> Tuple[bool, str]:
        """
        Evaluates candidate trade against active portfolio.
        Returns: (is_allowed: bool, reason: str)
        """
        if not active_positions:
            return True, "Portfolio flat. No cross-asset correlation risk."

        cand_dir = 1 if candidate_type == mt5.ORDER_TYPE_BUY else -1
        cand_returns = self.get_returns(candidate_symbol, timeframe)
        if cand_returns is None:
            return True, f"Insufficient price history for {candidate_symbol}; gate bypassed."

        for pos in active_positions:
            if pos.symbol == candidate_symbol:
                return False, f"Direct Asset Lockout: Existing active position on {candidate_symbol}."

            active_dir = 1 if pos.type == mt5.ORDER_TYPE_BUY else -1
            active_returns = self.get_returns(pos.symbol, timeframe)
            if active_returns is None:
                continue

            # Align series lengths
            min_len = min(len(cand_returns), len(active_returns))
            s1 = cand_returns.iloc[-min_len:]
            s2 = active_returns.iloc[-min_len:]

            rho = float(s1.corr(s2))
            if np.isnan(rho):
                continue

            effective_co_movement = rho * (cand_dir * active_dir)

            if effective_co_movement > self.correlation_threshold:
                side_cand = "BUY" if cand_dir == 1 else "SELL"
                side_act = "BUY" if active_dir == 1 else "SELL"
                return False, (
                    f"Blocked by Correlation Gate: {candidate_symbol} {side_cand} vs "
                    f"{pos.symbol} {side_act} (rho={rho:+.2f}, Psi={effective_co_movement:+.2f} > {self.correlation_threshold})"
                )

        return True, "Correlation risk within safe bounds."

if __name__ == "__main__":
    LOGIN = 278017866
    PASSWORD = "H@ngkook3695"
    SERVER = "Exness-MT5Trial5"

    if mt5.initialize() and mt5.login(login=LOGIN, password=PASSWORD, server=SERVER):
        gate = CorrelationMatrixGate(lookback_bars=50, correlation_threshold=0.70)
        symbols = ["USDJPY", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD"]
        
        print("=" * 80)
        print("     QUANT NEXUS // ROLLING CORRELATION MATRIX (M15)")
        print("=" * 80)
        corr_matrix = gate.compute_matrix(symbols)
        if not corr_matrix.empty:
            print(corr_matrix.round(3).to_string())
        print("-" * 80)
        
        active_pos = mt5.positions_get()
        print(f"Active Positions in Memory: {len(active_pos) if active_pos else 0}")
        if active_pos:
            test_order_sym = "EURUSD"
            test_order_type = mt5.ORDER_TYPE_BUY
            allowed, reason = gate.evaluate_order_risk(test_order_sym, test_order_type, list(active_pos))
            print(f"• Pre-Trade Gate Simulation [{test_order_sym} BUY]: Allowed={allowed}")
            print(f"  Reason: {reason}")
        print("=" * 80)
        mt5.shutdown()
