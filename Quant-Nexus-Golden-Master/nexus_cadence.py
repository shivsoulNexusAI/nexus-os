from dataclasses import asdict
from gsr_engine import GSREngine
gsr_tracker = GSREngine(lookback=50, z_threshold=2.0)
from typing import Optional
import logging
from dxy_gold_correlation_vision import ApexDXYGoldVision, CorrelationState

gold_vision = ApexDXYGoldVision(gold_symbol="XAUUSD", lookback_bars=40)

def validate_xauusd_preflight_gate(signal_side: str, base_volume: float) -> tuple[bool, float, str, Optional[CorrelationState]]:
    """Evaluates cross-market DXY/Gold correlation and SMT divergence prior to execution."""
    _logger = logging.getLogger("NexusCadence")
    try:
        state: CorrelationState = gold_vision.evaluate_vision()
    except Exception as e:
        _logger.error(f"[GoldVision] Failed to evaluate DXY-Gold correlation: {e}")
        return True, base_volume, f"Vision bypass (Evaluation Error: {e})", None

    _logger.info(
        f"[GoldVision] XAUUSD Pre-Flight Check | Regime: {state.regime} (rho={state.pearson_corr}) | "
        f"SMT: {state.smt_divergence} | DXY Bias: {state.dxy_bias} | Target Side: {signal_side}"
    )

    if state.regime == "DECOUPLED_RISK_OFF":
        _logger.warning(f"[GoldVision] Execution BLOCKED: Decoupled Risk-Off Regime (rho={state.pearson_corr})")
        return False, 0.0, f"Blocked by Decoupled Regime (rho={state.pearson_corr})", state

    if signal_side.upper() == "BUY":
        if state.dxy_bias == "BULLISH" and state.smt_divergence != "BULLISH_SMT":
            _logger.warning("[GoldVision] Execution REJECTED: Buying Gold into Bullish DXY without Bullish SMT.")
            return False, 0.0, "Macro Mismatch: Gold BUY into Bullish DXY without SMT", state
    elif signal_side.upper() == "SELL":
        if state.dxy_bias == "BEARISH" and state.smt_divergence != "BEARISH_SMT":
            _logger.warning("[GoldVision] Execution REJECTED: Shorting Gold into Bearish DXY without Bearish SMT.")
            return False, 0.0, "Macro Mismatch: Gold SELL into Bearish DXY without SMT", state

    adjusted_volume = round(base_volume * state.gold_signal_multiplier, 2)
    adjusted_volume = max(0.01, min(adjusted_volume, 0.10))
    return True, adjusted_volume, f"Passed Gate (Multiplier: {state.gold_signal_multiplier}x)", state



def get_gsr_telemetry_payload():
    try:
        metrics = gsr_tracker.compute_metrics()
        return asdict(metrics) if metrics else None
    except Exception as e:
        return {"error": str(e)}

