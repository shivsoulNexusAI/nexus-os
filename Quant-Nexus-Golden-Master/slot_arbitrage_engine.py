"""
Quant Nexus: Elite Omega Engine
Module: slot_arbitrage_engine.py
Description: Evaluates running positions vs queued high-conviction setups.
             Executes partial harvests or scratch liquidations to free slots
             for asymmetric institutional order flow.
"""

from datetime import datetime, timezone
import MetaTrader5 as mt5
import pandas as pd


class SlotArbitrageEngine:
    def __init__(self, max_slots: int = 4, edge_delta_threshold: float = 0.12, stagnation_minutes: int = 45):
        self.max_slots = max_slots
        self.edge_delta_threshold = edge_delta_threshold
        self.stagnation_minutes = stagnation_minutes

    def get_open_positions_metrics(self) -> list:
        """
        Audits all open positions and computes Opportunity Cost Score (OCS) and hold durations.
        """
        positions = mt5.positions_get()
        if not positions:
            return []

        metrics = []
        now = datetime.now(timezone.utc).timestamp()

        for p in positions:
            symbol = p.symbol
            ticket = p.ticket
            entry = p.price_open
            current_price = p.price_current
            sl = p.sl
            point = mt5.symbol_info(symbol).point
            risk_dist = abs(entry - sl) if sl > 0 else (250 * point)
            if risk_dist == 0:
                risk_dist = 250 * point

            floating_diff = (current_price - entry) if p.type == 0 else (entry - current_price)
            r_multiple = floating_diff / risk_dist

            elapsed_minutes = (now - p.time) / 60.0

            # Opportunity Cost Score: Penalizes stagnant low-R trades over time
            # Low OCS = prime candidate for harvest or scratch liquidation
            ocs = r_multiple - (0.05 * (elapsed_minutes / 15.0))

            metrics.append({
                "ticket": ticket,
                "symbol": symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "profit": p.profit,
                "r_multiple": round(r_multiple, 2),
                "elapsed_minutes": round(elapsed_minutes, 1),
                "ocs": round(ocs, 4)
            })

        metrics.sort(key=lambda x: x["ocs"])
        return metrics

    def evaluate_arbitrage(self, candidate_symbol: str, candidate_direction: str, candidate_edge: float) -> dict:
        """
        Determines whether to liquidate/harvest the weakest runner to fund the candidate trade.
        """
        positions_metrics = self.get_open_positions_metrics()

        # If slots are still available, no rotation is needed
        if len(positions_metrics) < self.max_slots:
            return {
                "decision": "DIRECT_EXECUTE",
                "reason": f"Slots available ({len(positions_metrics)}/{self.max_slots} occupied)",
                "target_ticket": None
            }

        weakest = positions_metrics[0]

        # Calculate conviction difference
        # Normalize weakest OCS to a relative probability scale
        weakest_conviction = max(0.40, min(0.75, 0.50 + (weakest["r_multiple"] * 0.10)))
        edge_gap = candidate_edge - weakest_conviction

        # Stagnation rule: Trade held > 45 mins with negligible R
        is_stagnant = (weakest["elapsed_minutes"] >= self.stagnation_minutes and abs(weakest["r_multiple"]) <= 0.35)

        if edge_gap >= self.edge_delta_threshold or is_stagnant:
            action_type = "SCRATCH_ROTATION" if weakest["r_multiple"] < 0.8 else "PROFIT_HARVEST_ROTATION"
            return {
                "decision": "ROTATE_SLOT",
                "action": action_type,
                "target_ticket": weakest["ticket"],
                "target_symbol": weakest["symbol"],
                "weakest_r": weakest["r_multiple"],
                "candidate_symbol": candidate_symbol,
                "candidate_edge": candidate_edge,
                "edge_gap": round(edge_gap, 4),
                "reason": f"Rotating {weakest['symbol']} (R={weakest['r_multiple']:+.2f}, Age={weakest['elapsed_minutes']}m) for higher conviction {candidate_symbol} (Edge={candidate_edge:.1%})"
            }

        return {
            "decision": "SUPPRESS_CANDIDATE",
            "reason": f"Slots full. Candidate edge ({candidate_edge:.1%}) does not exceed weakest runner {weakest['symbol']} by threshold ({self.edge_delta_threshold:.0%})",
            "target_ticket": None
        }

    def execute_slot_harvest(self, ticket: int) -> bool:
        """
        Executes immediate market liquidation on the targeted ticket.
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False

        p = pos[0]
        symbol = p.symbol
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": p.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": p.magic,
            "comment": "Omega: Slot Arbitrage Harvest",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        res = mt5.order_send(req)
        return res.retcode == mt5.TRADE_RETCODE_DONE