CONFIDENCE_THRESHOLD = 80.0
# --- INSTITUTIONAL 1K RISK LIMITS ---
DEFAULT_LOT_SIZE = 0.01
DAILY_EQUITY_FLOOR = 950.00
# ------------------------------------
"""
SHIVSOUL SOVEREIGN NEXUS // CONFLUENCE GATING ENGINE (confluence_engine.py)
Validates M15 tactical setup against H1/H4 macro horizons.
"""
from typing import Tuple, Dict, Any
from mtf_engine import mtf_engine

class ConfluenceEngine:
    def __init__(self, min_confluence_score: float = 0.70):
        self.min_confluence = min_confluence_score

    def verify_alignment(self, symbol: str, tactical_direction: str) -> Tuple[bool, float, str, Dict[str, Any]]:
        """
        Returns:
            passed (bool): True if macro trend does not oppose tactical setup.
            confluence_score (float): 0.0 - 1.0 confidence scalar.
            alignment_status (str): Narrative summary.
            macro_data (dict): Detailed H1/H4 levels.
        """
        macro = mtf_engine.get_macro_structure(symbol)
        h1_bias = macro["H1"]["bias"]
        h4_bias = macro["H4"]["bias"]

        # Expected direction mapping
        expected_macro = "BULLISH" if tactical_direction == "BUY" else "BEARISH"
        opposing_macro = "BEARISH" if tactical_direction == "BUY" else "BULLISH"

        score = 0.50

        # Hard Veto: Both H1 and H4 actively oppose tactical entry
        if h1_bias == opposing_macro and h4_bias == opposing_macro:
            return (
                False,
                0.20,
                f"HARD_VETO: Tactical {tactical_direction} opposes active H1({h1_bias}) & H4({h4_bias}) trend",
                macro
            )

        # Full Confluence: Both H1 and H4 align with tactical entry
        if h1_bias == expected_macro and h4_bias == expected_macro:
            score = 1.00
            status = f"PERFECT_ALIGNMENT: H1({h1_bias}) & H4({h4_bias})"
        # Strong Confluence: H1 aligns, H4 neutral or consolidating
        elif h1_bias == expected_macro:
            score = 0.85
            status = f"FAVORABLE_MOMENTUM: H1({h1_bias}) aligned, H4({h4_bias})"
        # Macro Supported: H4 aligns, H1 pulling back
        elif h4_bias == expected_macro:
            score = 0.75
            status = f"MACRO_SUPPORT: H4({h4_bias}) aligned, H1({h1_bias}) pullback"
        else:
            score = 0.50
            status = f"CHOP_ALERT: H1({h1_bias}) / H4({h4_bias}) neutral consolidation"

        passed = score >= self.min_confluence
        return passed, score, status, macro

confluence_engine = ConfluenceEngine()

def analyze_institutional_market_structure(*args, **kwargs):
    """Fallback stub for institutional market structure analysis."""
    return {"aligned": True, "score": 1.0, "reason": "Confluence engine active"}

def analyze_institutional_market_structure(*args, **kwargs):
    """Fallback stub for institutional market structure analysis."""
    return {"aligned": True, "score": 1.0, "reason": "Confluence engine active"}


