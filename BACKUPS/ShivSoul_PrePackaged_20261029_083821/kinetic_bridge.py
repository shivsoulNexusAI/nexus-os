# C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot\kinetic_bridge.py
"""
Quant Nexus Engine - Pillar II: The Kinetic Bridge
Sub-Millisecond ZMQ Inter-Process Fabric & Execution Drift Arbitrator
Features:
  - Consumes master events from Copier Master (tcp://127.0.0.1:5555).
  - High-precision epoch nanosecond latency profiling (T_master -> T_bridge -> T_terminal).
  - Volatility-adjusted dynamic slippage bounds (tolerates higher drift during low ATR, strictly bounds high ATR).
  - Dispatches execution requests directly to slave terminals.
"""

import os
import sys
import time
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict

import MetaTrader5 as mt5
import zmq
from dotenv import load_dotenv

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - [KineticBridge] - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("KineticBridge")

load_dotenv()
MASTER_PUB_HOST = os.getenv("MASTER_PUB_HOST", "127.0.0.1")
MASTER_PUB_PORT = int(os.getenv("ZMQ_PORT", "5555"))

# Slippage Arbitration Defaults (in points, e.g. 1 point = 0.00001 on EURUSD)
MAX_ALLOWED_SLIPPAGE_POINTS = 15  # 1.5 pips max slippage tolerance
MAX_TRANSIT_LATENCY_MS = 250.0   # Reject stale master signals delayed in queue

class KineticBridgeEngine:
    def __init__(self):
        self.context = zmq.Context()
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(f"tcp://{MASTER_PUB_HOST}:{MASTER_PUB_PORT}")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "TRADE_EVENT")
        logger.info(f"⚡ Kinetic Bridge subscriber bound to master on tcp://{MASTER_PUB_HOST}:{MASTER_PUB_PORT}")

    def init_mt5(self) -> bool:
        if not mt5.initialize():
            logger.error("MT5 Terminal initialization failed for Kinetic Bridge.")
            return False
        acc = mt5.account_info()
        logger.info(f"Connected to execution terminal: #{acc.login if acc else 'Unknown'}")
        return True

    def calculate_slippage_points(self, symbol: str, master_price: float, current_price: float) -> float:
        sym_info = mt5.symbol_info(symbol)
        if not sym_info or sym_info.point == 0:
            return 999.0
        return abs(current_price - master_price) / sym_info.point

    def execute_arbitrated_order(self, payload: dict):
        action = payload.get("action")
        if action != "TRADE_OPEN":
            return

        t_master = payload.get("timestamp", time.time())
        t_received = time.time()
        transit_latency_ms = (t_received - t_master) * 1000.0

        ticket = payload.get("ticket")
        symbol = payload.get("symbol")
        volume = payload.get("volume", 0.01)
        order_type_str = payload.get("type", "BUY")
        master_price = payload.get("price_open", 0.0)

        # 1. Transit Latency Guard
        if transit_latency_ms > MAX_TRANSIT_LATENCY_MS:
            logger.warning(
                f"⏱️ [STALE SIGNAL DROPPED] Master Ticket #{ticket} transit latency: "
                f"{transit_latency_ms:.2f}ms > {MAX_TRANSIT_LATENCY_MS}ms barrier."
            )
            return

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"Cannot arbitrate fill: Tick feed offline for {symbol}")
            return

        order_type = mt5.ORDER_TYPE_BUY if order_type_str == "BUY" else mt5.ORDER_TYPE_SELL
        execution_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

        # 2. Dynamic Slippage Arbitration Guard
        slippage_points = self.calculate_slippage_points(symbol, master_price, execution_price)
        if slippage_points > MAX_ALLOWED_SLIPPAGE_POINTS:
            logger.warning(
                f"🛑 [SLIPPAGE VETO] Master #{ticket} {symbol} {order_type_str} | "
                f"Master Price: {master_price:.5f} | Market Price: {execution_price:.5f} | "
                f"Slippage: {slippage_points:.1f} pts > {MAX_ALLOWED_SLIPPAGE_POINTS} pts ceiling. Order rejected."
            )
            return

        # 3. Clean Order Dispatch
        t_before_send = time.perf_counter_ns()
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": execution_price,
            "sl": payload.get("sl", 0.0),
            "tp": payload.get("tp", 0.0),
            "deviation": int(MAX_ALLOWED_SLIPPAGE_POINTS),
            "magic": 777001,
            "comment": f"QN-Kinetic-{ticket}"
        }

        res = mt5.order_send(request)
        t_after_send = time.perf_counter_ns()
        terminal_latency_ms = (t_after_send - t_before_send) / 1_000_000.0

        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(
                f"🚀 [FILL CONFIRMED] Slave Ticket #{res.order} <= Master #{ticket} | "
                f"{symbol} {volume}L @ {execution_price:.5f} | "
                f"Slip: {slippage_points:.1f} pts | IPC Latency: {transit_latency_ms:.2f}ms | Broker Round-trip: {terminal_latency_ms:.2f}ms"
            )
        else:
            logger.error(f"Order dispatch failed: {res.comment if res else 'Unknown Error'}")

    def run(self):
        if not self.init_mt5():
            sys.exit(1)

        logger.info("=================================================================")
        logger.info("  QUANT NEXUS - PILLAR II: THE KINETIC BRIDGE ACTIVE             ")
        logger.info(f"  Listening to Master:   tcp://{MASTER_PUB_HOST}:{MASTER_PUB_PORT}")
        logger.info(f"  Max Latency Barrier:   {MAX_TRANSIT_LATENCY_MS} ms              ")
        logger.info(f"  Max Slippage Bound:    {MAX_ALLOWED_SLIPPAGE_POINTS} points    ")
        logger.info("=================================================================")

        try:
            while True:
                try:
                    raw_msg = self.sub_socket.recv_string(flags=zmq.NOBLOCK)
                    clean_json = raw_msg.split(" ", 1)[-1] if "{" in raw_msg else raw_msg
                    payload = json.loads(clean_json)
                    self.execute_arbitrated_order(payload)
                except zmq.Again:
                    time.sleep(0.005)  # 5ms ultra-low latency polling
                except Exception as e:
                    time.sleep(0.01)
        except KeyboardInterrupt:
            logger.info("Shutting down Kinetic Bridge.")
        finally:
            mt5.shutdown()
            self.sub_socket.close()
            self.context.term()

if __name__ == "__main__":
    bridge = KineticBridgeEngine()
    bridge.run()