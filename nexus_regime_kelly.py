import numpy as np
import MetaTrader5 as mt5

class NexusRegimeKelly:
    STATE_EXPANSION = 0
    STATE_COMPRESSION = 1
    STATE_TURBULENCE = 2

    def __init__(self, target_risk_pct=0.01, max_kelly_fraction=0.025, min_kelly_fraction=0.002):
        self.base_risk = target_risk_pct
        self.max_kelly = max_kelly_fraction
        self.min_kelly = min_kelly_fraction

    def detect_regime(self, symbol):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 50)
        if rates is None or len(rates) < 40:
            return self.STATE_COMPRESSION, "COMPRESSION (FALLBACK)", 0.5
        closes = rates['close'].astype(float)
        highs = rates['high'].astype(float)
        lows = rates['low'].astype(float)
        log_ret = np.diff(np.log(closes))
        mean_drift = np.mean(log_ret[-12:])
        std_drift = np.std(log_ret[-12:]) + 1e-8
        hl_ratio = np.log(highs / np.maximum(lows, 1e-8))
        parkinson_vol = np.sqrt((1.0 / (4.0 * np.log(2.0))) * np.mean(hl_ratio[-14:]**2))
        baseline_parkinson = np.sqrt((1.0 / (4.0 * np.log(2.0))) * np.mean(hl_ratio**2)) + 1e-8
        vol_expansion_ratio = parkinson_vol / baseline_parkinson
        sym_info = mt5.symbol_info(symbol)
        spread_pts = sym_info.spread if sym_info else 10.0
        atr_approx = np.mean(highs[-14:] - lows[-14:])
        spread_cost_ratio = (spread_pts * (sym_info.point if sym_info else 0.01)) / (atr_approx + 1e-8)
        if vol_expansion_ratio > 2.2 or spread_cost_ratio > 0.15:
            return self.STATE_TURBULENCE, "TURBULENCE (CIRCUIT BREAKER)", 0.0
        drift_significance = abs(mean_drift) / std_drift
        if drift_significance > 0.45 and 0.8 <= vol_expansion_ratio <= 2.2:
            return self.STATE_EXPANSION, "EXPANSION (TREND RUNNER)", 1.0
        else:
            return self.STATE_COMPRESSION, "COMPRESSION (SCALP ONLY)", 0.45

    def compute_kelly_lots(self, symbol, ml_prob, sl_points, reward_ratio=2.33):
        state_id, state_name, regime_scalar = self.detect_regime(symbol)
        if regime_scalar == 0.0:
            return 0.0, state_name, "Turbulence Circuit Breaker Active - Risk Zeroed"
        b = max(reward_ratio, 1.0)
        p = np.clip(ml_prob, 0.01, 0.99)
        full_kelly = (p * (b + 1.0) - 1.0) / b
        dynamic_risk_fraction = max(0.0, full_kelly * 0.5) * regime_scalar
        effective_risk_pct = np.clip(dynamic_risk_fraction, self.min_kelly, self.max_kelly)
        acc = mt5.account_info()
        equity = acc.equity if acc else 10000.0
        dollar_risk = equity * effective_risk_pct
        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return 0.01, state_name, "Symbol info unavailable"
        point = sym_info.point
        tick_size = sym_info.trade_tick_size
        tick_value = sym_info.trade_tick_value
        if point == 0 or sl_points <= 0 or tick_size == 0 or tick_value == 0:
            return sym_info.volume_min, state_name, "Invalid calculation metrics"
        loss_per_lot = (sl_points / tick_size) * tick_value
        raw_lot = dollar_risk / (loss_per_lot + 1e-8)
        vol_step = sym_info.volume_step
        vol_min = sym_info.volume_min
        vol_max = sym_info.volume_max
        calculated_lot = round(round(raw_lot / vol_step) * vol_step, 2)
        final_lot = max(vol_min, min(calculated_lot, vol_max))
        audit_msg = f"Regime: {state_name} | ML: {p*100:.1f}% | Risk: {effective_risk_pct*100:.2f}% (${dollar_risk:.2f}) | Sized Lot: {final_lot}"
        return final_lot, state_name, audit_msg
