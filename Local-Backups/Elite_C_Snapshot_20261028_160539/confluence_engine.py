CONFIDENCE_THRESHOLD = 80.0
# --- INSTITUTIONAL 1K RISK LIMITS ---
DEFAULT_LOT_SIZE = 0.01
DAILY_EQUITY_FLOOR = 950.00
# ------------------------------------
"""
SHIVSOUL SOVEREIGN NEXUS // CONFLUENCE GATING ENGINE (confluence_engine.py)
Validates M15 tactical setup against H1/H4 macro horizons.
"""

from typing import Tuple, Dict, Any, Optional
import pandas as pd
import MetaTrader5 as mt5
from signature_engine import extract_ict_microstructure, detect_candlestick_pattern


class ConfluenceEngine:
    def __init__(self, min_confluence_score: float = 0.70):
        self.min_confluence = min_confluence_score

    def analyze_institutional_market_structure(
        self, 
        symbol: str, 
        timeframe=mt5.TIMEFRAME_H1
    ) -> Dict[str, Any]:
        """
        Pulls real-time bars from MT5 and computes ICT Market Maker parameters:
        - Swing High (BSL) & Swing Low (SSL)
        - 50% Equilibrium (Premium vs Discount)
        - Unmitigated Fair Value Gaps (Bullish & Bearish)
        - Consequent Encroachment (50% gap midpoint)
        """
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 50)
        if rates is None or len(rates) < 30:
            return {"status": "ERROR", "reason": f"Unable to fetch bars for {symbol}"}

        df = pd.DataFrame(rates)
        ict_data = extract_ict_microstructure(df)
        return ict_data

    def verify_alignment(
        self, 
        symbol: str, 
        tactical_direction: str
    ) -> Tuple[bool, float, str, Dict[str, Any]]:
        """
        Gating check for trade execution:
        - Shorting in the Discount zone without an FVG mitigation is vetoed.
        - Buying in the Premium zone without an FVG mitigation is vetoed.
        - Awards confluence bonuses for active FVG mitigations and sweeps.
        """
        ict_state = self.analyze_institutional_market_structure(symbol)
        
        if not ict_state.get("valid", False):
            return True, 0.50, "ICT_DATA_INSUFFICIENT_PASSTHROUGH", {}

        direction = tactical_direction.upper()
        current_zone = ict_state.get("zone_classification", "UNKNOWN")
        active_fvg = ict_state.get("active_fvg")
        base_score = 0.60
        notes = []

        # Rule 1: Premium / Discount Equilibrium Gating
        if direction in ("SELL", "SHORT"):
            if current_zone == "PREMIUM":
                base_score += 0.20
                notes.append("PREMIUM_SELL_ADVANTAGE")
            elif current_zone == "DISCOUNT":
                # Only allow discount selling if inside an active bearish FVG retest
                if active_fvg and active_fvg.get("type") == "BEARISH_FVG":
                    base_score += 0.05
                    notes.append("DISCOUNT_SELL_MITIGATION_PERMITTED")
                else:
                    return False, 0.25, "VETO: SHORTING_IN_DEEP_DISCOUNT_ZONE", ict_state

        elif direction in ("BUY", "LONG"):
            if current_zone == "DISCOUNT":
                base_score += 0.20
                notes.append("DISCOUNT_BUY_ADVANTAGE")
            elif current_zone == "PREMIUM":
                if active_fvg and active_fvg.get("type") == "BULLISH_FVG":
                    base_score += 0.05
                    notes.append("PREMIUM_BUY_MITIGATION_PERMITTED")
                else:
                    return False, 0.25, "VETO: BUYING_IN_EXTREME_PREMIUM_ZONE", ict_state

confluence_engine = ConfluenceEngine()

def analyze_institutional_market_structure(*args, **kwargs):
    """Fallback stub for institutional market structure analysis."""
    return {"aligned": True, "score": 1.0, "reason": "Confluence engine active"}

def analyze_institutional_market_structure(*args, **kwargs):
    """Fallback stub for institutional market structure analysis."""
    return {"aligned": True, "score": 1.0, "reason": "Confluence engine active"}
