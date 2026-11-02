"""
NEXUS MICROSTRUCTURE ENGINE v2.1 (Production Robust)
====================================================================
Subsystems:
  1. Real-Time Order Flow Imbalance (OFI) & Absorption Engine
  2. Spread Blowout Gating & Jump-Diffusion Circuit Breakers
  3. Dynamic Half-Kelly Capital Sizing Module
  4. Temporal Alpha Decay & Lifecycle Manager
====================================================================
"""

import time
from datetime import datetime, timezone, timedelta
import numpy as np
import MetaTrader5 as mt5

class NexusMicrostructureEngine:
    def __init__(self, symbol: str, lookback_ticks: int = 200):
        self.symbol = symbol
        self.lookback_ticks = lookback_ticks
        self.tick_buffer = []
        
        # Risk Constants
        self.MAX_SPREAD_RATIO = 2.5
        self.TIME_EXPIRY_BARS = 12
        self.KELLY_DAMPENER = 0.50

    def sync_ticks(self) -> bool:
        """Fetches tick-level execution stream from MT5 bridge reliably."""
        # 1. Ensure symbol is explicitly enabled in Market Watch
        if not mt5.symbol_select(self.symbol, True):
            print(f"[-] Failed to select {self.symbol} in Market Watch: {mt5.last_error()}")
            return False

        # 2. Query ticks from 10 minutes ago to now (UTC)
        utc_from = datetime.now(timezone.utc) - timedelta(minutes=10)
        ticks = mt5.copy_ticks_from(self.symbol, utc_from, self.lookback_ticks, mt5.COPY_TICKS_ALL)
        
        # Fallback to copy_ticks_range if copy_ticks_from yields empty
        if ticks is None or len(ticks) == 0:
            utc_to = datetime.now(timezone.utc)
            ticks = mt5.copy_ticks_range(self.symbol, utc_from, utc_to, mt5.COPY_TICKS_ALL)

        if ticks is None or len(ticks) == 0:
            return False

        # Retain the most recent N ticks
        self.tick_buffer = ticks[-self.lookback_ticks:]
        return True

    def evaluate_spread_regime(self) -> tuple[bool, float, float]:
        """Jump-Diffusion Guard: Halt execution when spread > 2.5x median."""
        if len(self.tick_buffer) < 20:
            return True, 0.0, 0.0

        spreads = [t['ask'] - t['bid'] for t in self.tick_buffer]
        current_spread = spreads[-1]
        rolling_median = float(np.median(spreads))
        
        if rolling_median <= 0:
            return True, current_spread, rolling_median

        spread_ratio = current_spread / rolling_median
        is_safe = spread_ratio <= self.MAX_SPREAD_RATIO
        return is_safe, current_spread, rolling_median

    def calculate_order_flow_imbalance(self) -> dict:
        """Calculates Cont-Kukanov-Stoikov OFI and Passive Absorption."""
        if len(self.tick_buffer) < 20:
            return {"ofi_z": 0.0, "absorption_ratio": 0.0, "passive_absorption": False}

        bids = np.array([t['bid'] for t in self.tick_buffer])
        asks = np.array([t['ask'] for t in self.tick_buffer])
        
        if 'bid_volume' in self.tick_buffer.dtype.names and 'ask_volume' in self.tick_buffer.dtype.names:
            bid_vols = np.array([t['bid_volume'] for t in self.tick_buffer], dtype=float)
            ask_vols = np.array([t['ask_volume'] for t in self.tick_buffer], dtype=float)
        else:
            bid_vols = np.array([t['volume'] if 'volume' in self.tick_buffer.dtype.names else 1.0 for t in self.tick_buffer], dtype=float)
            ask_vols = bid_vols.copy()

        bid_vols[bid_vols == 0] = 1.0
        ask_vols[ask_vols == 0] = 1.0

        delta_bids = np.diff(bids)
        delta_asks = np.diff(asks)

        delta_wb = np.where(delta_bids > 0, bid_vols[1:], np.where(delta_bids == 0, bid_vols[1:] - bid_vols[:-1], 0))
        delta_wa = np.where(delta_asks > 0, 0, np.where(delta_asks == 0, ask_vols[1:] - ask_vols[:-1], -ask_vols[1:]))

        ofi_series = delta_wb - delta_wa
        mean_ofi = np.mean(ofi_series)
        std_ofi = np.std(ofi_series) + 1e-8
        ofi_z = float((ofi_series[-1] - mean_ofi) / std_ofi)

        price_displacement = abs(bids[-1] - bids[0])
        total_vol = float(np.sum(bid_vols) + np.sum(ask_vols))
        absorption_ratio = float(total_vol / (price_displacement + 1e-5))

        absorption_divergence = False
        if ofi_z < -1.5 and delta_bids[-1] >= 0:
            absorption_divergence = True
        elif ofi_z > 1.5 and delta_asks[-1] <= 0:
            absorption_divergence = True

        return {
            "ofi_z": round(ofi_z, 3),
            "absorption_ratio": round(absorption_ratio, 2),
            "passive_absorption": absorption_divergence
        }

    def calculate_fractional_kelly_size(self, balance: float, edge: float, payoff_ratio: float = 2.0) -> float:
        """Volatility-Adjusted Fractional Kelly Allocation."""
        p = max(0.01, min(0.99, edge))
        b = max(0.5, payoff_ratio)
        
        raw_kelly = (p * (b + 1.0) - 1.0) / b
        if raw_kelly <= 0:
            return 0.0025

        scaled_risk = raw_kelly * self.KELLY_DAMPENER
        final_risk = float(np.clip(scaled_risk, 0.0025, 0.0250))
        return round(final_risk, 4)

    def evaluate_temporal_decay(self, ticket: int, open_time: int, timeframe_seconds: int = 60) -> dict:
        """Temporal Alpha Decay Manager."""
        current_time = int(time.time())
        elapsed_bars = (current_time - open_time) // timeframe_seconds
        expired = elapsed_bars >= self.TIME_EXPIRY_BARS
        return {
            "ticket": ticket,
            "elapsed_bars": elapsed_bars,
            "max_bars": self.TIME_EXPIRY_BARS,
            "trigger_time_exit": expired
        }
