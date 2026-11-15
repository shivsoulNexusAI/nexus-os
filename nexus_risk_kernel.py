"""
QUANTNEXUS RISK KERNEL (v2.0 Institutional Hardened)
Implements bounded fractional Kelly Criterion (Half-Kelly), leverage envelopes,
consecutive loss de-risking, and tick-exact broker lot quantization.
"""
import math
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("NexusRiskKernel")

# Institutional Envelopes
MAX_PORTFOLIO_RISK_CAP = 0.030   # 3.0% maximum aggregate risk on any single trade setup
MIN_PORTFOLIO_RISK_FLOOR = 0.002 # 0.20% minimum risk floor to maintain mathematical edge
MAX_LEVERAGE_CAP = 10.0          # Max notional trade leverage permitted (Notional / Equity <= 10x)
KELLY_FRACTION = 0.50            # Strict Half-Kelly multiplier
MAX_CONSECUTIVE_LOSS_PENALTY = 3 # Consecutive loss count where de-risking engages

class NexusRiskKernel:
    def __init__(
        self,
        kelly_fraction: float = KELLY_FRACTION,
        max_risk_cap: float = MAX_PORTFOLIO_RISK_CAP,
        min_risk_floor: float = MIN_PORTFOLIO_RISK_FLOOR,
        max_leverage: float = MAX_LEVERAGE_CAP
    ):
        self.c = kelly_fraction
        self.max_risk_cap = max_risk_cap
        self.min_risk_floor = min_risk_floor
        self.max_leverage = max_leverage

    def compute_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        consecutive_losses: int = 0
    ) -> float:
        """
        Calculates bounded Half-Kelly fraction with consecutive-loss attenuation.
        Returns fraction of equity to risk on trade [min_risk_floor, max_risk_cap].
        """
        # Sanitization & boundary checks
        p = max(0.01, min(0.99, win_rate))
        q = 1.0 - p
        b = (avg_win / abs(avg_loss)) if abs(avg_loss) > 1e-6 else 1.0

        # Unconstrained Continuous Kelly
        f_star = (p * (b + 1.0) - 1.0) / b

        # Negative Edge or Zero Edge -> Apply minimum structural floor or zero
        if f_star <= 0.0:
            logger.warning(f"[EDGE-WARNING] Kelly fraction non-positive (f*={f_star:.4f}, p={p:.2f}, b={b:.2f}). Enforcing minimal floor.")
            f_bounded = self.min_risk_floor
        else:
            # Scale to Half-Kelly
            f_scaled = f_star * self.c
            # Bound within institutional risk envelopes
            f_bounded = max(self.min_risk_floor, min(self.max_risk_cap, f_scaled))

        # Dynamic De-risking: Attenuate risk during drawdowns / consecutive loss streaks
        if consecutive_losses >= MAX_CONSECUTIVE_LOSS_PENALTY:
            decay_factor = 0.75 ** (consecutive_losses - MAX_CONSECUTIVE_LOSS_PENALTY + 1)
            decay_factor = max(0.25, decay_factor) # Max 75% attenuation
            f_bounded = max(self.min_risk_floor, f_bounded * decay_factor)
            logger.info(f"[DE-RISK] Consecutive losses ({consecutive_losses}) engaged: Applied {decay_factor:.2f}x attenuation -> Risk: {f_bounded*100:.2f}%")

        return round(f_bounded, 5)

    def calculate_bounded_lot_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss_price: float,
        symbol_info: Dict[str, Any],
        win_rate: float = 0.55,
        avg_win: float = 1.8,
        avg_loss: float = 1.0,
        consecutive_losses: int = 0
    ) -> Dict[str, Any]:
        """
        Calculates tick-exact, leverage-capped, and quantized lot volume.
        """
        if equity <= 0:
            return {"lot_size": 0.0, "reason": "ZERO_OR_NEGATIVE_EQUITY"}

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 1e-6:
            return {"lot_size": 0.0, "reason": "INVALID_SL_DISTANCE"}

        # Extract broker contract specifications
        tick_size = symbol_info.get("trade_tick_size", 0.00001)
        tick_value = symbol_info.get("trade_tick_value", 1.0)
        contract_size = symbol_info.get("trade_contract_size", 100000.0)
        vol_min = symbol_info.get("volume_min", 0.01)
        vol_max = symbol_info.get("volume_max", 100.0)
        vol_step = symbol_info.get("volume_step", 0.01)

        # 1. Compute target risk cash capital
        risk_fraction = self.compute_kelly_fraction(win_rate, avg_win, avg_loss, consecutive_losses)
        target_cash_risk = equity * risk_fraction

        # 2. Derive raw volume from stop loss distance and point value
        # Cash Risk = Volume * (SL_Distance / Tick_Size) * Tick_Value
        loss_per_lot = (sl_distance / tick_size) * tick_value
        if loss_per_lot <= 0.0:
            return {"lot_size": 0.0, "reason": "INVALID_LOSS_PER_LOT"}

        raw_lots = target_cash_risk / loss_per_lot

        # 3. Notional Value & Maximum Leverage Enveloping
        # Notional Exposure = Lots * Contract Size * Entry Price
        notional_value = raw_lots * contract_size * entry_price
        max_allowed_notional = equity * self.max_leverage
        
        if notional_value > max_allowed_notional:
            capped_lots = max_allowed_notional / (contract_size * entry_price)
            logger.warning(
                f"[LEVERAGE-CLAMP] Raw lot ({raw_lots:.3f}) exceeded {self.max_leverage}x leverage cap "
                f"(${notional_value:,.2f} >${max_allowed_notional:,.2f}). Clamped to {capped_lots:.3f} lots."
            )
            raw_lots = capped_lots

        # 4. Discrete Broker Step Quantization (Floor rounding to eliminate over-risk)
        steps = math.floor(raw_lots / vol_step)
        quantized_lots = round(steps * vol_step, 4)

        # Clamp within broker bounds
        if quantized_lots < vol_min:
            # If target risk permits at least 70% of min lot exposure, grant min lot; otherwise abort
            min_lot_cash_risk = vol_min * loss_per_lot
            if min_lot_cash_risk <= (target_cash_risk * 1.30):
                quantized_lots = vol_min
            else:
                logger.info(f"[MIN-LOT-ABORT] Min lot {vol_min} risk (${min_lot_cash_risk:.2f}) exceeds target risk (${target_cash_risk:.2f}) by >30%. Execution suppressed.")
                return {"lot_size": 0.0, "reason": "BELOW_MIN_LOT_RISK_THRESHOLD"}

        quantized_lots = min(quantized_lots, vol_max)
        actual_cash_risk = quantized_lots * loss_per_lot
        actual_risk_pct = (actual_cash_risk / equity) * 100.0

        return {
            "lot_size": quantized_lots,
            "target_cash_risk": round(target_cash_risk, 2),
            "actual_cash_risk": round(actual_cash_risk, 2),
            "actual_risk_pct": round(actual_risk_pct, 2),
            "kelly_fraction": risk_fraction,
            "leverage_used": round((quantized_lots * contract_size * entry_price) / equity, 2),
            "reason": "OK"
        }

if __name__ == "__main__":
    print("=== TESTING NEXUS RISK KERNEL v2.0 ===")
    kernel = NexusRiskKernel()
    
    mock_symbol = {
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "trade_contract_size": 100000.0,
        "volume_min": 0.01,
        "volume_max": 50.0,
        "volume_step": 0.01
    }

    # Baseline 1.5R edge test
    res = kernel.calculate_bounded_lot_size(
        equity=988.78,
        entry_price=1.05200,
        stop_loss_price=1.05050, # 15 pip SL
        symbol_info=mock_symbol,
        win_rate=0.55,
        avg_win=27.0,
        avg_loss=15.0,
        consecutive_losses=0
    )
    print("Standard Trade Sizing Result:")
    for k, v in res.items():
        print(f"  • {k:<20}: {v}")

    # Micro-SL Divergence / Leverage Cap Test
    res_tight = kernel.calculate_bounded_lot_size(
        equity=988.78,
        entry_price=1.05200,
        stop_loss_price=1.05190, # 1 pip SL (divergence stress)
        symbol_info=mock_symbol,
        win_rate=0.60,
        avg_win=30.0,
        avg_loss=10.0,
        consecutive_losses=0
    )
    print("\nTight SL (1 pip) Leverage-Cap Stress Result:")
    for k, v in res_tight.items():
        print(f"  • {k:<20}: {v}")
    print("======================================")
