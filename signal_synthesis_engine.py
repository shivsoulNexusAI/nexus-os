"""
QuantNexus Signal Synthesis & Composite Edge Scoring Engine
Analyzes MSS, FVGs, and SMT Correlated Divergences across M5/M15 microstructures.
Outputs normalized Edge Confluence Score (0 - 100).
"""
import sys
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import MetaTrader5 as mt5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("SignalSynthesis")

# Asset correlation pairings for Smart Money Technique (SMT) Divergence
SMT_PAIRS = {
    "EURUSD": "GBPUSD",
    "GBPUSD": "EURUSD",
    "USDJPY": "EURUSD" # Inverted correlation proxy
}

class SignalSynthesisEngine:
    def __init__(self, terminal_path: str = r"C:\MT5_Quant_278061453\terminal64.exe"):
        self.terminal_path = terminal_path

    def _ensure_mt5(self) -> bool:
        if not mt5.initialize(path=self.terminal_path):
            log.error("Failed to connect to MT5 terminal at %s", self.terminal_path)
            return False
        return True

    def detect_market_structure_shift(self, symbol: str) -> Dict[str, Any]:
        """Detects displacement and swing breaks on M15."""
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 30)
        if rates is None or len(rates) < 20:
            return {"mss": "NONE", "score": 0, "swing_level": None}

        highs = [r['high'] for r in rates[:-1]]
        lows = [r['low'] for r in rates[:-1]]
        current_close = rates[-1]['close']

        recent_swing_high = max(highs[-10:-1])
        recent_swing_low = min(lows[-10:-1])

        # Bullish MSS: M15 Close broke through recent swing high with displacement
        if current_close > recent_swing_high:
            displacement = (current_close - recent_swing_high)
            return {"mss": "BULLISH", "score": 35, "swing_level": recent_swing_high, "disp": displacement}

        # Bearish MSS: M15 Close broke through recent swing low with displacement
        if current_close < recent_swing_low:
            displacement = (recent_swing_low - current_close)
            return {"mss": "BEARISH", "score": 35, "swing_level": recent_swing_low, "disp": displacement}

        return {"mss": "NONE", "score": 0, "swing_level": None}

    def detect_fair_value_gap(self, symbol: str) -> Dict[str, Any]:
        """Detects 3-candle Fair Value Gap imbalances on M5."""
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 6)
        if rates is None or len(rates) < 4:
            return {"fvg": "NONE", "score": 0, "top": None, "bottom": None}

        # Candle references: -4 (candle 1), -3 (candle 2), -2 (candle 3)
        c1, c2, c3 = rates[-4], rates[-3], rates[-2]

        # Bullish FVG: Low of candle 3 is above high of candle 1
        if c3['low'] > c1['high']:
            gap_size = c3['low'] - c1['high']
            return {"fvg": "BULLISH", "score": 30, "top": c3['low'], "bottom": c1['high'], "gap": gap_size}

        # Bearish FVG: High of candle 3 is below low of candle 1
        if c3['high'] < c1['low']:
            gap_size = c1['low'] - c3['high']
            return {"fvg": "BEARISH", "score": 30, "top": c1['low'], "bottom": c3['high'], "gap": gap_size}

        return {"fvg": "NONE", "score": 0, "top": None, "bottom": None}

    def detect_smt_divergence(self, primary: str, secondary: str) -> Dict[str, Any]:
        """Detects Smart Money Technique non-concurrence (divergence) between correlated pairs."""
        r1 = mt5.copy_rates_from_pos(primary, mt5.TIMEFRAME_M15, 0, 15)
        r2 = mt5.copy_rates_from_pos(secondary, mt5.TIMEFRAME_M15, 0, 15)

        if r1 is None or r2 is None or len(r1) < 10 or len(r2) < 10:
            return {"smt": False, "score": 0, "type": "NONE"}

        # High/Low comparisons of previous swing
        p_high_prior, p_high_curr = max(r['high'] for r in r1[:7]), max(r['high'] for r in r1[7:])
        s_high_prior, s_high_curr = max(r['high'] for r in r2[:7]), max(r['high'] for r in r2[7:])

        # Direct Correlation Divergence (EURUSD vs GBPUSD)
        # One creates a Higher High, while the other creates a Lower High
        p_made_hh = p_high_curr > p_high_prior
        s_made_hh = s_high_curr > s_high_prior

        if p_made_hh != s_made_hh:
            div_type = "BEARISH SMT (Swept Highs)" if p_made_hh else "BULLISH SMT (Liquidity Displaced)"
            return {"smt": True, "score": 25, "type": div_type, "pair": f"{primary}/{secondary}"}

        return {"smt": False, "score": 0, "type": "NONE"}

    def is_killzone_active(self) -> Dict[str, Any]:
        """Validates ICT London / NY Killzone windows."""
        now_utc = datetime.now(timezone.utc)
        h = now_utc.hour

        # London: 07:00 - 10:00 UTC | NY AM: 12:00 - 15:00 UTC | NY PM: 18:00 - 20:00 UTC
        if 7 <= h < 10:
            return {"active": True, "session": "LONDON_OPEN", "score": 10}
        elif 12 <= h < 15:
            return {"active": True, "session": "NY_AM_BULLET", "score": 10}
        elif 18 <= h < 20:
            return {"active": True, "session": "NY_PM_REVERSAL", "score": 10}

        return {"active": False, "session": "OFF_HOURS", "score": 0}

    def synthesize_edge(self, symbol: str) -> Dict[str, Any]:
        """Aggregates all components into a comprehensive 0-100 edge score."""
        if not self._ensure_mt5():
            return {"error": "MT5 Unreachable"}

        try:
            mss = self.detect_market_structure_shift(symbol)
            fvg = self.detect_fair_value_gap(symbol)
            
            corr_pair = SMT_PAIRS.get(symbol, "GBPUSD")
            smt = self.detect_smt_divergence(symbol, corr_pair)
            kz = self.is_killzone_active()

            total_score = mss["score"] + fvg["score"] + smt["score"] + kz["score"]

            bias = "NEUTRAL"
            if total_score >= 60:
                if mss["mss"] == "BULLISH" or fvg["fvg"] == "BULLISH":
                    bias = "STRONG_BULLISH" if total_score >= 75 else "MODERATE_BULLISH"
                elif mss["mss"] == "BEARISH" or fvg["fvg"] == "BEARISH":
                    bias = "STRONG_BEARISH" if total_score >= 75 else "MODERATE_BEARISH"

            return {
                "symbol": symbol,
                "composite_edge_score": total_score,
                "bias": bias,
                "is_actionable": total_score >= 75,
                "components": {
                    "mss": mss,
                    "fvg": fvg,
                    "smt": smt,
                    "session": kz
                }
            }
        finally:
            mt5.shutdown()

if __name__ == "__main__":
    synthesizer = SignalSynthesisEngine()
    symbols_to_test = ["EURUSD", "GBPUSD", "USDJPY"]
    
    print("=" * 80)
    print(f"[*] QUANTNEXUS SIGNAL SYNTHESIS PROBE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    for s in symbols_to_test:
        edge = synthesizer.synthesize_edge(s)
        print(f"\n[+] ASSET: {s} | Edge Score: {edge.get('composite_edge_score', 0)}/100 | Bias: {edge.get('bias')}")
        comps = edge.get("components", {})
        print(f"    • MSS Shift : {comps.get('mss', {}).get('mss')} (+{comps.get('mss', {}).get('score')} pts)")
        print(f"    • FVG Gap   : {comps.get('fvg', {}).get('fvg')} (+{comps.get('fvg', {}).get('score')} pts)")
        print(f"    • SMT Div   : {comps.get('smt', {}).get('type')} (+{comps.get('smt', {}).get('score')} pts)")
        print(f"    • Killzone  : {comps.get('session', {}).get('session')} (+{comps.get('session', {}).get('score')} pts)")
        print(f"    • Actionable: {edge.get('is_actionable')}")
    print("=" * 80)
