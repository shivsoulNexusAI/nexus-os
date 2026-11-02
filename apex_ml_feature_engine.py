import math
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone

class ApexMicrostructureML:
    @staticmethod
    def extract_features(symbol: str):
        # 1. Microstructure Rates (M5)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 25:
            return None

        # Garman-Klass Volatility
        gk_elements = []
        for r in rates[-14:]:
            o, h, l, c = r['open'], r['high'], r['low'], r['close']
            if o <= 0 or l <= 0: continue
            term1 = 0.5 * (math.log(h / l) ** 2)
            term2 = (2.0 * math.log(2.0) - 1.0) * (math.log(c / o) ** 2)
            gk_elements.append(term1 - term2)
        gk_vol = math.sqrt(sum(gk_elements) / len(gk_elements)) if gk_elements else 0.001

        # 2. Aldemon Liquidity Penetration
        recent_high = max(r['high'] for r in rates[-20:-2])
        recent_low = min(r['low'] for r in rates[-20:-2])
        curr = rates[-1]
        prev = rates[-2]
        atr = sum(r['high'] - r['low'] for r in rates[-14:]) / 14.0

        sweep_depth_pts = 0.0
        bias = "NEUTRAL"
        if prev['low'] < recent_low and curr['close'] > recent_low:
            bias = "BULLISH_SWEEP"
            sweep_depth_pts = (recent_low - prev['low']) / (atr if atr > 0 else 1.0)
        elif prev['high'] > recent_high and curr['close'] < recent_high:
            bias = "BEARISH_SWEEP"
            sweep_depth_pts = (prev['high'] - recent_high) / (atr if atr > 0 else 1.0)

        # 3. High-Frequency Tick-Delta Flow
        ticks = mt5.copy_ticks_from(symbol, datetime.now(timezone.utc), 150, mt5.COPY_TICKS_ALL)
        ofi_delta = 0.0
        spread_ratio = 1.0
        if ticks is not None and len(ticks) >= 30:
            bid_vol = sum(t.volume if t.volume > 0 else 1.0 for t in ticks if t.flags & mt5.TICK_FLAG_SELL)
            ask_vol = sum(t.volume if t.volume > 0 else 1.0 for t in ticks if t.flags & mt5.TICK_FLAG_BUY)
            total_v = bid_vol + ask_vol
            ofi_delta = (ask_vol - bid_vol) / total_v if total_v > 0 else 0.0
            spreads = [t.ask - t.bid for t in ticks]
            med_sp = np.median(spreads)
            curr_sp = ticks[-1].ask - ticks[-1].bid
            spread_ratio = curr_sp / med_sp if med_sp > 0 else 1.0

        # Feature Vector Formulation
        # [GK_Vol, OFI_Delta, Sweep_Depth, Spread_Ratio, ATR]
        features = np.array([gk_vol, ofi_delta, sweep_depth_pts, spread_ratio, atr], dtype=np.float32)

        # Empirical Logistic / Microstructure Edge Scoring
        # Intercept + Weights derived from institutional order flow calibration
        z = -0.20 + (1.85 * sweep_depth_pts) + (1.20 * abs(ofi_delta)) - (0.85 * max(0, spread_ratio - 1.0))
        empirical_p = 1.0 / (1.0 + math.exp(-z))
        
        # Dampen if OFI opposes the structural sweep
        if bias == "BULLISH_SWEEP" and ofi_delta < -0.20:
            empirical_p *= 0.85
        elif bias == "BEARISH_SWEEP" and ofi_delta > 0.20:
            empirical_p *= 0.85

        return {
            "bias": bias,
            "probability": round(min(0.92, max(0.40, empirical_p)), 4),
            "features": features,
            "atr": atr,
            "spread_ratio": spread_ratio,
            "ofi": round(ofi_delta, 3)
        }

if __name__ == "__main__":
    import MetaTrader5 as mt5
    if mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe", portable=True):
        print("⚡ APEX ML FEATURE EXTRACTION TEST")
        for sym in ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "USDJPY"]:
            res = ApexMicrostructureML.extract_features(sym)
            if res:
                print(f"[{sym:<7}] Bias: {res['bias']:<14} | P(Win): {res['probability']*100:>5.1f}% | OFI: {res['ofi']:>+5.2f} | SpreadRatio: {res['spread_ratio']:.2f}x")
        mt5.shutdown()
