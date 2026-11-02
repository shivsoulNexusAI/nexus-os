"""
Quant Nexus Engine - Pillar I: The Sentinel Eye
Real-time Volume-Synchronized Probability of Toxicity (VPIN) & Flow Imbalance Engine.
Broadcasts toxicity regimes to downstream copier and allocator daemons via ZeroMQ.
"""

import os
import sys
import time
import math
import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple

import MetaTrader5 as mt5
import zmq
from dotenv import load_dotenv

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - [SentinelEye] - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SentinelEye")

load_dotenv()
PUB_PORT = int(os.getenv("SENTINEL_PUB_PORT", "5556"))
SYMBOL = os.getenv("PRIMARY_SYMBOL", "EURUSD")

# Microstructure Configuration
BUCKET_VOLUME_UNITS = 50.0   # Standardized lot-equivalent volume per bucket
WINDOW_BUCKETS = 20          # Rolling window size (N)
TOXICITY_THRESHOLD = 0.65    # VPIN barrier above which orders are deemed toxic
POLL_SLEEP_SEC = 0.05

@dataclass
class VolumeBucket:
    buy_vol: float = 0.0
    sell_vol: float = 0.0
    filled: bool = False

    @property
    def total_volume(self) -> float:
        return self.buy_vol + self.sell_vol

    @property
    def imbalance(self) -> float:
        return abs(self.buy_vol - self.sell_vol)

class SentinelEyeEngine:
    def __init__(self, symbol: str = SYMBOL, bucket_size: float = BUCKET_VOLUME_UNITS, window: int = WINDOW_BUCKETS):
        self.symbol = symbol
        self.bucket_size = bucket_size
        self.window = window
        self.buckets = deque(maxlen=window)
        self.current_bucket = VolumeBucket()
        self.last_tick_time = 0
        self.last_price = 0.0

        # ZeroMQ Publisher
        self.context = zmq.Context()
        self.publisher = self.context.socket(zmq.PUB)
        self.publisher.bind(f"tcp://127.0.0.1:{PUB_PORT}")
        logger.info(f"Sentinel Eye Publisher broadcasting on tcp://127.0.0.1:{PUB_PORT}")

    def init_mt5(self) -> bool:
        if not mt5.initialize():
            logger.error("MT5 Initialization failed for Sentinel Eye.")
            return False
        if not mt5.symbol_select(self.symbol, True):
            logger.error(f"Failed to subscribe to symbol: {self.symbol}")
            return False
        logger.info(f"Sentinel Eye hooked into MT5 tick stream for {self.symbol}")
        return True

    def _classify_tick(self, tick) -> Tuple[float, float]:
        price = (tick.bid + tick.ask) / 2.0
        volume = float(tick.volume_real) if tick.volume_real > 0 else float(tick.volume)
        if volume <= 0:
            volume = 1.0

        if self.last_price == 0.0:
            self.last_price = price
            return volume * 0.5, volume * 0.5

        if price > self.last_price:
            buy_vol = volume
            sell_vol = 0.0
        elif price < self.last_price:
            buy_vol = 0.0
            sell_vol = volume
        else:
            mid = (tick.bid + tick.ask) / 2.0
            if tick.last >= mid:
                buy_vol = volume
                sell_vol = 0.0
            else:
                buy_vol = 0.0
                sell_vol = volume

        self.last_price = price
        return buy_vol, sell_vol

    def ingest_tick(self, tick) -> Optional[float]:
        buy_v, sell_v = self._classify_tick(tick)
        needed = self.bucket_size - self.current_bucket.total_volume

        inflow_total = buy_v + sell_v
        if inflow_total <= needed:
            self.current_bucket.buy_vol += buy_v
            self.current_bucket.sell_vol += sell_v
            if self.current_bucket.total_volume >= self.bucket_size:
                self.current_bucket.filled = True
                self.buckets.append(self.current_bucket)
                self.current_bucket = VolumeBucket()
        else:
            fraction = needed / inflow_total if inflow_total > 0 else 0
            self.current_bucket.buy_vol += buy_v * fraction
            self.current_bucket.sell_vol += sell_v * fraction
            self.current_bucket.filled = True
            self.buckets.append(self.current_bucket)

            remainder_buy = buy_v * (1.0 - fraction)
            remainder_sell = sell_v * (1.0 - fraction)
            self.current_bucket = VolumeBucket(buy_vol=remainder_buy, sell_vol=remainder_sell)

        if len(self.buckets) < self.window:
            return None

        total_imbalance = sum(b.imbalance for b in self.buckets)
        vpin = total_imbalance / (self.window * self.bucket_size)
        return round(float(vpin), 4)

    def run(self):
        if not self.init_mt5():
            return

        logger.info("=================================================================")
        logger.info("  QUANT NEXUS - PILLAR I: THE SENTINEL EYE ACTIVE                ")
        logger.info(f"  Target Asset:          {self.symbol}                           ")
        logger.info(f"  Volume Bucket Size:    {self.bucket_size} units                ")
        logger.info(f"  Window Size:           {self.window} buckets                   ")
        logger.info(f"  Toxicity Threshold:    {TOXICITY_THRESHOLD}                    ")
        logger.info("=================================================================")

        try:
            while True:
                tick = mt5.symbol_info_tick(self.symbol)
                if tick and tick.time_msc != self.last_tick_time:
                    self.last_tick_time = tick.time_msc
                    vpin = self.ingest_tick(tick)

                    if vpin is not None:
                        is_toxic = vpin >= TOXICITY_THRESHOLD
                        state_str = "⚠️ TOXIC FLOW SWEEP" if is_toxic else "✅ BALANCED BOOK"
                        
                        payload = (
                            f"MICROSTRUCTURE_REGIME symbol={self.symbol} "
                            f"vpin={vpin:.4f} toxic={'1' if is_toxic else '0'} "
                            f"bid={tick.bid:.5f} ask={tick.ask:.5f} ts={tick.time_msc}"
                        )
                        self.publisher.send_string(payload)

                        if is_toxic:
                            logger.warning(f"{state_str} | VPIN: {vpin:.4f} >= {TOXICITY_THRESHOLD} | Halting Aggressive Entry")
                
                time.sleep(POLL_SLEEP_SEC)

        except KeyboardInterrupt:
            logger.info("Sentinel Eye shut down requested.")
        finally:
            mt5.shutdown()
            self.publisher.close()
            self.context.term()

if __name__ == "__main__":
    sentinel = SentinelEyeEngine()
    sentinel.run()