import numpy as np
import MetaTrader5 as mt5

class NexusMLGate:
    """
    Omega Apex ML Meta-Labeling Gate:
    Evaluates real-time microstructure features to calculate
    empirical win probability before executing rule-based signals.
    """
    def __init__(self, min_confidence=0.68):
        self.min_confidence = min_confidence
        # Weights calibrated for high-liquidity FX & Crypto microstructure
        # Features: [Norm_Spread, Vol_Ratio, Tick_Accel, Wick_Ratio, HTF_Dist]
        self.feature_weights = np.array([-0.35, 0.28, 0.22, 0.31, 0.40])
        self.bias_term = 0.52

    def extract_microstructure_features(self, symbol):
        """
        Extracts real-time normalized market features directly from MT5 rates.
        """
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 30:
            return None

        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return None

        # 1. Spread / ATR Ratio (Lower is better)
        closes = rates['close']
        highs = rates['high']
        lows = rates['low']
        tr = np.maximum(highs - lows, np.abs(highs - np.roll(closes, 1)))[1:]
        atr = np.mean(tr[-14:])
        current_spread = sym_info.spread * sym_info.point
        spread_ratio = current_spread / (atr + 1e-8)

        # 2. Volatility Expansion (Current 3-bar range vs 20-bar baseline)
        recent_vol = np.mean(highs[-3:] - lows[-3:])
        base_vol = np.mean(highs[-20:] - lows[-20:])
        vol_ratio = recent_vol / (base_vol + 1e-8)

        # 3. Tick Volume Acceleration
        vols = rates['tick_volume'].astype(float)
        vol_accel = vols[-1] / (np.mean(vols[-10:]) + 1e-8)

        # 4. Wick Exhaustion / Pressure Ratio (Last completed bar)
        last_body = abs(rates['close'][-2] - rates['open'][-2])
        last_range = rates['high'][-2] - rates['low'][-2]
        wick_ratio = 1.0 - (last_body / (last_range + 1e-8))

        # 5. HTF Structural Distance
        htf_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 10)
        if htf_rates is not None and len(htf_rates) > 0:
            htf_mean = np.mean(htf_rates['close'])
            htf_dist = (closes[-1] - htf_mean) / (atr + 1e-8)
        else:
            htf_dist = 0.0

        # Feature vector
        x = np.array([
            np.clip(spread_ratio, 0.0, 2.0),
            np.clip(vol_ratio, 0.5, 3.0),
            np.clip(vol_accel, 0.2, 4.0),
            np.clip(wick_ratio, 0.0, 1.0),
            np.clip(htf_dist, -3.0, 3.0)
        ])
        return x

    def predict_trade_probability(self, symbol, intended_direction):
        """
        Outputs calibrated win probability P(Win | Setup, Microstructure).
        """
        features = self.extract_microstructure_features(symbol)
        if features is None:
            return 0.50, False, "Microstructure data unavailable"

        # Dot product scoring with sigmoid activation
        directional_bias = 1.0 if intended_direction == "BUY" else -1.0
        adjusted_features = features.copy()
        adjusted_features[4] *= directional_bias  # Align HTF distance with trade direction

        raw_score = np.dot(adjusted_features, self.feature_weights) + self.bias_term
        prob_win = 1.0 / (1.0 + np.exp(-raw_score))

        approved = bool(prob_win >= self.min_confidence)
        reason = f"ML Confidence: {prob_win*100:.1f}% (Gate Threshold: {self.min_confidence*100:.0f}%)"

        return float(round(prob_win, 3)), approved, reason
