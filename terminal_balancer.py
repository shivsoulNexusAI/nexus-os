from nexus_logging_guard import get_rotating_logger
"""
QUANTNEXUS MULTI-TERMINAL BALANCER (v1.1 Institutional Production)
Orchestrates health-audited, equity-proportional order distribution across
the three verified MetaTrader 5 terminal instances on the 1GB VPS.
"""
import os
import gc
import sys
import time
import math
import logging
from typing import Dict, List, Optional
import MetaTrader5 as mt5

sys.path.append("C:/Quant-Nexus-Eng")
from nexus_telegram import send_alert

LOG_PATH = "C:/Quant-Nexus-Eng/terminal_balancer.log"
logger = get_rotating_logger("TerminalBalancer", "terminal_balancer.log")

TERMINAL_REGISTRY = [
    {
        "id": "TERM_QUANT_278061453",
        "path": "C:/MT5_Quant_278061453/terminal64.exe",
        "weight_override": None,
        "enabled": True
    },
    {
        "id": "TERM_HFT_278041671",
        "path": "C:/MT5_HFT_278041671/terminal64.exe",
        "weight_override": None,
        "enabled": True
    },
    {
        "id": "TERM_PENDING_278041169",
        "path": "C:/MT5_Pending_278041169/terminal64.exe",
        "weight_override": None,
        "enabled": True
    }
]

DRY_RUN = True  # Safe verification mode; flip to False for live cluster order execution

class MultiTerminalBalancer:
    def __init__(self, registry: List[dict] = TERMINAL_REGISTRY):
        self.registry = registry

    def audit_terminal_health(self) -> List[dict]:
        """
        Sequentially connects to each terminal instance, validates account state
        and trade authorization, and captures live equity for volume weighting.
        """
        active_nodes = []
        for term in self.registry:
            if not term.get("enabled", True):
                continue

            path = term["path"]
            term_id = term["id"]

            if not os.path.exists(path):
                logger.warning(f"[-] Terminal path does not exist on disk: {path}")
                continue

            if not mt5.initialize(path=path):
                err = mt5.last_error()
                logger.error(f"[-] Health Audit Failed for {term_id} (retcode={err})")
                continue

            acc = mt5.account_info()
            term_info = mt5.terminal_info()

            if acc and term_info:
                is_trade_allowed = bool(term_info.trade_allowed and acc.trade_allowed)
                node_data = {
                    "id": term_id,
                    "path": path,
                    "login": acc.login,
                    "server": acc.server,
                    "equity": float(acc.equity),
                    "balance": float(acc.balance),
                    "trade_allowed": is_trade_allowed,
                    "ping": term_info.ping_last
                }
                active_nodes.append(node_data)
                logger.info(
                    f"[HEALTH-OK] {term_id} | Login: #{acc.login} | Equity: ${acc.equity:,.2f} | "
                    f"TradeAllowed: {is_trade_allowed} | Ping: {term_info.ping_last / 1000:.1f}ms"
                )
            else:
                logger.error(f"[-] Failed to fetch account_info for {term_id}")

            mt5.shutdown()
            gc.collect()

        return active_nodes

    def calculate_lot_distribution(
        self,
        symbol: str,
        total_lots: float,
        active_nodes: List[dict]
    ) -> List[dict]:
        """
        Apportions aggregate lot size across online nodes based on relative equity,
        respecting broker volume_step and volume_min.
        """
        if not active_nodes:
            return []

        primary_path = active_nodes[0]["path"]
        vol_min, vol_max, vol_step = 0.01, 100.0, 0.01
        if mt5.initialize(path=primary_path):
            s_info = mt5.symbol_info(symbol)
            if s_info:
                vol_min = s_info.volume_min
                vol_max = s_info.volume_max
                vol_step = s_info.volume_step
            mt5.shutdown()
            gc.collect()

        total_equity = sum(n["equity"] for n in active_nodes)
        if total_equity <= 0.0:
            weights = [1.0 / len(active_nodes)] * len(active_nodes)
        else:
            weights = [n["equity"] / total_equity for n in active_nodes]

        distribution = []
        for idx, node in enumerate(active_nodes):
            raw_vol = total_lots * weights[idx]
            steps = round(raw_vol / vol_step)
            quantized_vol = round(steps * vol_step, 2)

            if quantized_vol < vol_min and total_lots >= vol_min:
                quantized_vol = vol_min
            quantized_vol = min(quantized_vol, vol_max)

            distribution.append({
                "id": node["id"],
                "path": node["path"],
                "login": node["login"],
                "equity": node["equity"],
                "weight_pct": round(weights[idx] * 100, 1),
                "allocated_lots": quantized_vol
            })

        return distribution

    def dispatch_balanced_order(
        self,
        symbol: str,
        order_type: int,
        total_lots: float,
        sl_price: float,
        tp_price: float,
        magic: int = 888101,
        comment: str = "QuantNexus-Bal"
    ) -> Dict:
        """
        Distributes and executes an institutional order across all healthy nodes.
        """
        active_nodes = [n for n in self.audit_terminal_health() if n["trade_allowed"]]
        if not active_nodes:
            logger.error("[-] No healthy MT5 terminals with trade permissions available.")
            return {"status": "ERROR", "reason": "NO_HEALTHY_NODES"}

        allocations = self.calculate_lot_distribution(symbol, total_lots, active_nodes)
        order_type_str = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
        mode_label = "[DRY-RUN]" if DRY_RUN else "[LIVE]"

        logger.info(
            f"{mode_label} Distributing {order_type_str} {total_lots:.2f} lots on {symbol} "
            f"across {len(allocations)} terminals."
        )

        results = []
        for alloc in allocations:
            node_id = alloc["id"]
            path = alloc["path"]
            vol = alloc["allocated_lots"]

            if vol <= 0.0:
                continue

            if DRY_RUN:
                logger.info(
                    f"{mode_label} Simulated routing to {node_id} (Login #{alloc['login']}) -> "
                    f"{vol:.2f} lots | SL: {sl_price} | TP: {tp_price}"
                )
                results.append({"id": node_id, "status": "SIMULATED", "volume": vol, "retcode": 10009})
            else:
                if not mt5.initialize(path=path):
                    logger.error(f"[-] Execution failed: cannot initialize {node_id}")
                    results.append({"id": node_id, "status": "INIT_FAILED", "volume": vol})
                    continue

                tick = mt5.symbol_info_tick(symbol)
                exec_price = (tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid) if tick else 0.0

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": vol,
                    "type": order_type,
                    "price": exec_price,
                    "sl": sl_price,
                    "tp": tp_price,
                    "deviation": 20,
                    "magic": magic,
                    "comment": comment,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }

                res = mt5.order_send(request)
                ret = getattr(res, "retcode", None)
                if ret == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"[ORDER-FILLED] {node_id} | Ticket: #{res.order} | Vol: {vol}")
                    results.append({"id": node_id, "status": "FILLED", "order": res.order, "volume": vol, "retcode": ret})
                else:
                    logger.error(f"[ORDER-REJECTED] {node_id} | Retcode: {ret}")
                    results.append({"id": node_id, "status": "REJECTED", "retcode": ret, "volume": vol})

                mt5.shutdown()
                gc.collect()

        dry_badge = "🧪 <b>[DRY-RUN]</b> " if DRY_RUN else "⚡ "
        alloc_summary = "\n".join([
            f"  • <code>{a['id']}</code>: <b>{a['allocated_lots']:.2f} lots</b> ({a['weight_pct']}%)"
            for a in allocations
        ])

        send_alert(
            "quant_alert_bot",
            f"{dry_badge}<b>MULTI-TERMINAL ORDER ROUTED</b>\n"
            f"• Symbol: <code>{symbol}</code> ({order_type_str})\n"
            f"• Aggregate Volume: <b>{total_lots:.2f} lots</b>\n"
            f"• Stop Loss: <code>{sl_price}</code> | TP: <code>{tp_price}</code>\n"
            f"<b>Terminal Distribution:</b>\n{alloc_summary}\n"
            f"• Status: {'Simulated Allocation' if DRY_RUN else 'Dispatched to Broker Nodes'}"
        )

        return {"status": "SUCCESS", "results": results, "allocations": allocations}


def main():
    logger.info("Initializing QuantNexus Multi-Terminal Balancer Audit...")
    balancer = MultiTerminalBalancer()
    
    print("\n=== STEP 1: AUDITING ALL 3 DISCOVERED TERMINAL NODES ===")
    nodes = balancer.audit_terminal_health()
    print(f"[+] Discovered {len(nodes)} active terminal instances.")

    print("\n=== STEP 2: SIMULATING 0.30 LOT ALLOCATION ACROSS NODES ===")
    allocations = balancer.calculate_lot_distribution("EURUSD", 0.30, nodes)
    for a in allocations:
        print(f"  • {a['id']:<24} | Equity: ${a['equity']:8,.2f} | Weight: {a['weight_pct']:5.1f}% | Lots: {a['allocated_lots']:.2f}")

    print("\n=== STEP 3: DISPATCHING SIMULATED BALANCED ORDER ===")
    res = balancer.dispatch_balanced_order(
        symbol="EURUSD",
        order_type=mt5.ORDER_TYPE_BUY,
        total_lots=0.30,
        sl_price=1.05000,
        tp_price=1.06500,
        comment="TestClusterDistribution"
    )
    print(f"[+] Balancer dispatch status: {res.get('status')}")
    print("=========================================================\n")

if __name__ == "__main__":
    main()
