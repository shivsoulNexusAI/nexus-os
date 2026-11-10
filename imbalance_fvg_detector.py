"""
QUANTNEXUS ORDER-FLOW IMBALANCE & FVG DETECTOR (v1.0 Production)
Detects structural three-candle Fair Value Gaps (FVG), Consequent Encroachment (CE),
relative tick volume displacement (RVOL), and real-time gap mitigation.
Engineered for 1GB VPS memory efficiency with minimal copy allocations.
"""
import gc
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_logging_guard import get_rotating_logger

logger = get_rotating_logger("ImbalanceDetector", "imbalance_fvg_detector.log")

class ImbalanceFVGDetector:
    def __init__(
        self,
        min_atr_factor: float = 0.40,
        min_body_ratio: float = 0.60,
        min_rvol_threshold: float = 1.30,
        atr_period: int = 14
    ):
        self.min_atr_factor = min_atr_factor
        self.min_body_ratio = min_body_ratio
        self.min_rvol = min_rvol_threshold
        self.atr_period = atr_period

    def calculate_atr(self, rates: Any) -> float:
        """Computes current ATR without loading pandas/numpy into VPS RAM."""
        if len(rates) < self.atr_period + 1:
            return 0.0001
        
        tr_sum = 0.0
        start_idx = len(rates) - self.atr_period
        for i in range(start_idx, len(rates)):
            h = rates[i]["high"]
            l = rates[i]["low"]
            c_prev = rates[i - 1]["close"]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_sum += tr
        return tr_sum / self.atr_period

    def scan_symbol_imbalances(
        self,
        symbol: str,
        timeframe: int = mt5.TIMEFRAME_M5,
        lookback_bars: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Scans recent historical bars for active unmitigated FVGs.
        """
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, lookback_bars)
        if rates is None or len(rates) < (self.atr_period + 5):
            return []

        atr = self.calculate_atr(rates)
        min_gap_size = atr * self.min_atr_factor

        # Median tick volume over previous 20 bars
        vols = [float(r["tick_volume"]) for r in rates[-25:-1]]
        vols.sort()
        median_vol = vols[len(vols) // 2] if vols else 1.0

        current_price = rates[-1]["close"]
        imbalances = []

        # Iterate 3-candle windows: C0=t-2, C1=t-1 (Displacement), C2=t
        # Leave last candle as active developing bar
        for i in range(2, len(rates) - 1):
            c0 = rates[i - 2]
            c1 = rates[i - 1]
            c2 = rates[i]

            # Displacement Candle Metrics
            body = abs(c1["close"] - c1["open"])
            candle_range = c1["high"] - c1["low"]
            if candle_range <= 1e-6:
                continue

            body_ratio = body / candle_range
            rvol = float(c1["tick_volume"]) / median_vol if median_vol > 0 else 1.0

            # Filter non-impulsive displacement
            if body_ratio < self.min_body_ratio or rvol < self.min_rvol:
                continue

            gap_type = None
            gap_low = 0.0
            gap_high = 0.0

            # 1. Bullish FVG (BISI): Low of C2 > High of C0
            if (c1["close"] > c1["open"]) and (c2["low"] > c0["high"]):
                gap_size = c2["low"] - c0["high"]
                if gap_size >= min_gap_size:
                    gap_type = "BULLISH_FVG"
                    gap_low = c0["high"]
                    gap_high = c2["low"]

            # 2. Bearish FVG (SIBI): High of C2 < Low of C0
            elif (c1["close"] < c1["open"]) and (c2["high"] < c0["low"]):
                gap_size = c0["low"] - c2["high"]
                if gap_size >= min_gap_size:
                    gap_type = "BEARISH_FVG"
                    gap_low = c2["high"]
                    gap_high = c0["low"]

            if gap_type is not None:
                ce_level = round(gap_low + 0.50 * (gap_high - gap_low), 5)
                fvg_bar_time = int(c1["time"])
                
                # Check subsequent bars for mitigation / fill
                mitigated = False
                fully_filled = False
                for j in range(i + 1, len(rates)):
                    bar = rates[j]
                    if gap_type == "BULLISH_FVG":
                        if bar["low"] <= ce_level:
                            mitigated = True
                        if bar["low"] <= gap_low:
                            fully_filled = True
                            break
                    else: # BEARISH_FVG
                        if bar["high"] >= ce_level:
                            mitigated = True
                        if bar["high"] >= gap_high:
                            fully_filled = True
                            break

                # Discard fully liquidated gaps
                if fully_filled:
                    continue

                dist_to_ce = abs(current_price - ce_level)
                imbalances.append({
                    "symbol": symbol,
                    "type": gap_type,
                    "bar_time": datetime.fromtimestamp(fvg_bar_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "gap_low": round(gap_low, 5),
                    "gap_high": round(gap_high, 5),
                    "ce_price": ce_level,
                    "gap_points": round((gap_high - gap_low) / (rates[0]["high"] * 0.0001 if "JPY" in symbol else 0.0001), 1),
                    "rvol": round(rvol, 2),
                    "body_ratio": round(body_ratio, 2),
                    "mitigated": mitigated,
                    "distance_pips": round(dist_to_ce / (0.01 if "JPY" in symbol else 0.0001), 1)
                })

        # Memory cleanup
        del rates
        return imbalances

if __name__ == "__main__":
    if not mt5.initialize():
        print("[-] MetaTrader 5 initialization failed:", mt5.last_error())
        sys.exit(1)

    print("\n================================================================================")
    print("      QUANTNEXUS HIGH-PROBABILITY ORDER-FLOW IMBALANCE & FVG SCANNER           ")
    print("================================================================================")

    detector = ImbalanceFVGDetector(min_atr_factor=0.35, min_body_ratio=0.60, min_rvol_threshold=1.20)
    watch_symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]

    total_active = 0
    for sym in watch_symbols:
        fvg_list = detector.scan_symbol_imbalances(sym, timeframe=mt5.TIMEFRAME_M5, lookback_bars=60)
        print(f"\n[SYMBOL: {sym}] - Found {len(fvg_list)} Active/Unmitigated Imbalance(s):")
        if not fvg_list:
            print("  • No unmitigated high-displacement FVGs found in recent 60 M5 bars.")
            continue

        for fvg in fvg_list:
            total_active += 1
            status_tag = "HALF-MITIGATED" if fvg["mitigated"] else "FRESH / UNTOUCHED"
            print(
                f"  • {fvg['type']:<11} | Bar: {fvg['bar_time']} | "
                f"Range: [{fvg['gap_low']} - {fvg['gap_high']}] | "
                f"CE: {fvg['ce_price']} | Dist: {fvg['distance_pips']} p | "
                f"RVOL: {fvg['rvol']}x | [{status_tag}]"
            )

    mt5.shutdown()
    gc.collect()
    print("\n" + "=" * 80)
    print(f"Total Active Imbalances Identified: {total_active}")
    print("================================================================================\n")
