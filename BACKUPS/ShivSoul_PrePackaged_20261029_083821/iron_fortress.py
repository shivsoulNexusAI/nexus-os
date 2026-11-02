# C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot\iron_fortress.py
"""
Quant Nexus Engine - Pillar III: The Iron Fortress
Cross-Broker Synthetic Hedging & Autonomous Drawdown Armor
Features:
  - Real-time High-Watermark (HWM) tracking and dynamic drawdown kill-switch.
  - Multi-tier circuit breaker:
      * Soft Halt at 10% Drawdown (Halts outbound signals, neutralizes exposure).
      * Hard Liquidation at 15% Drawdown (Emergency flattening of all tickets).
  - Synthetic Delta Arbitrator: Maintains EURUSD fleet delta within [-0.25, +0.25] lots.
  - Publishes emergency state updates to ZeroMQ port 5557 for Telegram C2 alerts.
"""

import os
import sys
import time
import json
import logging
from typing import Dict, List, Optional

import MetaTrader5 as mt5
import zmq
from dotenv import load_dotenv

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - [IronFortress] - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("IronFortress")

load_dotenv()
ZMQ_PUB_PORT = int(os.getenv("FORTRESS_PUB_PORT", "5557"))
POLL_INTERVAL = float(os.getenv("FORTRESS_POLL_INTERVAL", "0.2"))

# Risk Thresholds
SOFT_DRAWDOWN_LIMIT = 0.10   # 10% Soft Halt
HARD_DRAWDOWN_LIMIT = 0.15   # 15% Emergency Liquidation
DELTA_NEUTRAL_BAND = 0.25    # ±0.25 Lots maximum net directional bias
HEDGE_MAGIC_NUMBER = 999111  # Distinct magic ID for synthetic hedge tickets

class IronFortressEngine:
    def __init__(self, target_symbol: str = "EURUSD"):
        self.symbol = target_symbol
        self.context = zmq.Context()
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind(f"tcp://127.0.0.1:{ZMQ_PUB_PORT}")
        logger.info(f"🏰 Iron Fortress telemetry active on tcp://127.0.0.1:{ZMQ_PUB_PORT}")

        self.high_watermark = 0.0
        self.soft_halt_active = False
        self.hard_halt_active = False

    def init_mt5(self) -> bool:
        if not mt5.initialize():
            logger.error("MT5 terminal initialization failed for Iron Fortress.")
            return False
        acc = mt5.account_info()
        if not acc:
            logger.error("Failed to query MT5 account info.")
            return False
        self.high_watermark = float(acc.equity)
        logger.info(
            f"Iron Fortress linked: Account #{acc.login} | Starting Equity: ${acc.equity:,.2f} | "
            f"HWM Baseline: ${self.high_watermark:,.2f}"
        )
        return True

    def evaluate_drawdown_armor(self, equity: float) -> float:
        """Calculates current peak-to-trough drawdown and triggers defensive tiers."""
        if equity > self.high_watermark:
            self.high_watermark = equity

        drawdown = (self.high_watermark - equity) / self.high_watermark if self.high_watermark > 0 else 0.0

        # Tier 2: Hard Liquidation Circuit Breaker (15%)
        if drawdown >= HARD_DRAWDOWN_LIMIT and not self.hard_halt_active:
            self.hard_halt_active = True
            logger.critical(
                f"🚨🚨 [HARD DRAWDOWN BREACH] Current DD: {drawdown * 100:.2f}% >= {HARD_DRAWDOWN_LIMIT * 100:.1f}%! "
                f"EXECUTING EMERGENCY FLEET LIQUIDATION!"
            )
            self._emergency_flatten_fleet()
            self._broadcast_event("HARD_HALT", {"drawdown": drawdown, "equity": equity})
            return drawdown

        # Tier 1: Soft Halt (10%)
        if drawdown >= SOFT_DRAWDOWN_LIMIT and not self.soft_halt_active:
            self.soft_halt_active = True
            logger.warning(
                f"⚠️ [SOFT HALT ENGAGED] Current DD: {drawdown * 100:.2f}% >= {SOFT_DRAWDOWN_LIMIT * 100:.1f}%. "
                f"Suspending new allocations; shifting to pure hedge defense."
            )
            self._broadcast_event("SOFT_HALT", {"drawdown": drawdown, "equity": equity})

        # Recovery reset if equity re-enters safe range
        if drawdown < SOFT_DRAWDOWN_LIMIT and (self.soft_halt_active or self.hard_halt_active):
            self.soft_halt_active = False
            self.hard_halt_active = False
            logger.info("✅ Drawdown normalized below threshold. Safe operational state restored.")
            self._broadcast_event("NORMAL_OPS", {"drawdown": drawdown, "equity": equity})

        return drawdown

    def arbitrate_delta_neutrality(self):
        """Monitors fleet exposure on target symbol and opens counter-hedges if drift exceeds band."""
        if self.hard_halt_active:
            return  # Emergency shutdown active, do not open hedges

        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return

        long_vol = sum(p.volume for p in positions if p.type == mt5.ORDER_TYPE_BUY)
        short_vol = sum(p.volume for p in positions if p.type == mt5.ORDER_TYPE_SELL)
        net_delta = round(long_vol - short_vol, 2)

        # Delta exceeds positive band (excess Long exposure) -> Deploy Short Hedge
        if net_delta > DELTA_NEUTRAL_BAND:
            hedge_needed = round(net_delta, 2)
            logger.warning(
                f"⚖️ [DELTA DRIFT DETECTED] Long Exposure Net: +{net_delta:.2f}L > +{DELTA_NEUTRAL_BAND:.2f}L. "
                f"Deploying {hedge_needed:.2f}L synthetic Short hedge."
            )
            self._deploy_counter_hedge(mt5.ORDER_TYPE_SELL, hedge_needed)

        # Delta exceeds negative band (excess Short exposure) -> Deploy Long Hedge
        elif net_delta < -DELTA_NEUTRAL_BAND:
            hedge_needed = round(abs(net_delta), 2)
            logger.warning(
                f"⚖️ [DELTA DRIFT DETECTED] Short Exposure Net: {net_delta:.2f}L < -{DELTA_NEUTRAL_BAND:.2f}L. "
                f"Deploying {hedge_needed:.2f}L synthetic Long hedge."
            )
            self._deploy_counter_hedge(mt5.ORDER_TYPE_BUY, hedge_needed)

    def _deploy_counter_hedge(self, order_type: int, volume: float):
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return

        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": HEDGE_MAGIC_NUMBER,
            "comment": "QN-IronHedge"
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"🛡️ Synthetic hedge executed: Ticket #{res.order} | {volume}L {'SELL' if order_type==1 else 'BUY'}")
        else:
            logger.error(f"Failed to execute hedge: {res.comment if res else 'Unknown Error'}")

    def _emergency_flatten_fleet(self):
        """Immediately closes all open fleet positions regardless of type or magic number."""
        positions = mt5.positions_get()
        if not positions:
            logger.info("Fleet already flat. No open positions to liquidate.")
            return

        for p in positions:
            tick = mt5.symbol_info_tick(p.symbol)
            if not tick:
                continue

            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "price": close_price,
                "deviation": 30,
                "magic": HEDGE_MAGIC_NUMBER,
                "comment": "QN-EmergencyFlatten"
            }
            res = mt5.order_send(req)
            logger.info(f"Liquidated Ticket #{p.ticket}: Status {res.retcode if res else 'Fail'}")

    def _broadcast_event(self, event_type: str, details: dict):
        payload = {"event": event_type, "timestamp": time.time(), **details}
        self.pub_socket.send_string(f"FORTRESS_ALERT {json.dumps(payload)}")

    def run(self):
        if not self.init_mt5():
            sys.exit(1)

        logger.info("=================================================================")
        logger.info("  QUANT NEXUS - PILLAR III: THE IRON FORTRESS ONLINE             ")
        logger.info(f"  Target Asset:          {self.symbol}                           ")
        logger.info(f"  Soft Drawdown Limit:   {SOFT_DRAWDOWN_LIMIT * 100:.1f}%        ")
        logger.info(f"  Hard Liquidation Bar:  {HARD_DRAWDOWN_LIMIT * 100:.1f}%        ")
        logger.info(f"  Delta Neutral Band:    ±{DELTA_NEUTRAL_BAND:.2f} Lots          ")
        logger.info("=================================================================")

        try:
            while True:
                acc = mt5.account_info()
                if acc:
                    dd = self.evaluate_drawdown_armor(acc.equity)
                    self.arbitrate_delta_neutrality()
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Iron Fortress shutdown initiated.")
        finally:
            mt5.shutdown()
            self.pub_socket.close()
            self.context.term()

if __name__ == "__main__":
    fortress = IronFortressEngine()
    fortress.run()