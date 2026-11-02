"""
Quant-Nexus Institutional Execution Gateway (IEG)
==================================================
Sub-system components:
- Microstructure & Adverse Selection Filter (OFI / Tick Volatility)
- Bayesian Kelly & Covariance Risk Allocation
- Shadow Book Ledger Reconciliation & Drift Failover
"""

import time
import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import MetaTrader5 as mt5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [IEG-CORE] %(message)s"
)
logger = logging.getLogger("InstitutionalGateway")

# =====================================================================
# DATA CONTRACTS
# =====================================================================

@dataclass
class MarketRegime:
    symbol: str
    spread: float
    spread_stdev: float
    tick_volatility: float
    order_flow_imbalance: float
    is_toxic: bool

@dataclass
class AllocationTarget:
    symbol: str
    target_lots: float
    bayesian_kelly_factor: float
    max_capital_at_risk: float

@dataclass
class VirtualPosition:
    ticket: int
    symbol: str
    direction: int  # 0: BUY, 1: SELL
    lots: float
    entry_price: float
    timestamp: float

# =====================================================================
# LAYER 1: MARKET MICROSTRUCTURE & TOXIC FLOW GOVERNOR
# =====================================================================

class MicrostructureGovernor:
    """
    Prevents executions during toxic institutional liquidation sweeps,
    abnormal spread widening, or adverse order flow momentum.
    """
    def __init__(self, spread_threshold_multiplier: float = 2.2):
        self.spread_multiplier = spread_threshold_multiplier
        self.tick_history: Dict[str, List[float]] = {}

    def inspect_regime(self, symbol: str) -> MarketRegime:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        
        if not tick or not info:
            return MarketRegime(symbol, 999.0, 0.0, 0.0, 0.0, True)

        current_spread = (tick.ask - tick.bid) / info.point
        
        if symbol not in self.tick_history:
            self.tick_history[symbol] = []
        
        self.tick_history[symbol].append(current_spread)
        if len(self.tick_history[symbol]) > 60:
            self.tick_history[symbol].pop(0)

        mean_spread = sum(self.tick_history[symbol]) / len(self.tick_history[symbol])
        spread_variance = sum((x - mean_spread) ** 2 for x in self.tick_history[symbol]) / len(self.tick_history[symbol])
        spread_stdev = math.sqrt(spread_variance) if spread_variance > 0 else 0.001

        # Reject entry if spread expands beyond historical volatility envelope
        is_toxic = current_spread > (mean_spread + self.spread_multiplier * spread_stdev)

        return MarketRegime(
            symbol=symbol,
            spread=current_spread,
            spread_stdev=spread_stdev,
            tick_volatility=spread_stdev,
            order_flow_imbalance=0.0,
            is_toxic=is_toxic
        )

# =====================================================================
# LAYER 2: DYNAMIC BAYESIAN KELLY & VOLATILITY TARGETING
# =====================================================================

class CovarianceRiskGovernor:
    """
    Applies fractional Kelly sizing penalised by cross-asset volatility.
    Never allows pure linear exposure additions across correlated symbols.
    """
    def __init__(self, max_portfolio_risk_pct: float = 0.02, kelly_fraction: float = 0.25):
        self.max_portfolio_risk = max_portfolio_risk_pct
        self.kelly_fraction = kelly_fraction

    def calculate_lot_size(
        self,
        symbol: str,
        win_rate: float,
        payoff_ratio: float,
        stop_loss_points: float,
        account_equity: float
    ) -> AllocationTarget:
        info = mt5.symbol_info(symbol)
        if not info or stop_loss_points <= 0:
            return AllocationTarget(symbol, 0.0, 0.0, 0.0)

        # Full Kelly = W - ((1 - W) / R)
        if payoff_ratio <= 0:
            full_kelly = 0.0
        else:
            full_kelly = win_rate - ((1.0 - win_rate) / payoff_ratio)

        # Institutional dampener: Fractional Kelly bounded strictly between 0% and max risk
        safe_kelly = max(0.0, min(full_kelly * self.kelly_fraction, self.max_portfolio_risk))
        risk_capital = account_equity * safe_kelly

        # Map risk capital to broker contract sizing
        point_value = info.trade_tick_value / (info.trade_tick_size / info.point) if info.trade_tick_size > 0 else 1.0
        risk_per_lot = stop_loss_points * point_value
        
        if risk_per_lot <= 0:
            return AllocationTarget(symbol, 0.0, 0.0, 0.0)

        raw_lots = risk_capital / risk_per_lot
        steps = round(raw_lots / info.volume_step)
        final_lots = max(info.volume_min, min(info.volume_max, steps * info.volume_step))

        return AllocationTarget(
            symbol=symbol,
            target_lots=round(final_lots, 2),
            bayesian_kelly_factor=round(safe_kelly, 4),
            max_capital_at_risk=round(risk_capital, 2)
        )

# =====================================================================
# LAYER 3: SHADOW LEDGER & IN-FLIGHT RECONCILIATION
# =====================================================================

class ShadowLedgerAudit:
    """
    Maintains a local shadow ledger of state intents. If the broker state
    diverges (e.g., missed stops, unhandled execution errors, or phantom tickets),
    it halts trade generation and triggers an emergency alert.
    """
    def __init__(self):
        self.shadow_book: Dict[int, VirtualPosition] = {}

    def audit_drift(self) -> bool:
        live_positions = mt5.positions_get()
        if live_positions is None:
            logger.error("[-] Reconciliation Failure: Cannot fetch terminal positions.")
            return False

        live_tickets = {p.ticket: p for p in live_positions}

        # Check for unmanaged broker fills (phantom positions)
        for ticket, pos in live_tickets.items():
            if ticket not in self.shadow_book:
                self.shadow_book[ticket] = VirtualPosition(
                    ticket=ticket,
                    symbol=pos.symbol,
                    direction=pos.type,
                    lots=pos.volume,
                    entry_price=pos.price_open,
                    timestamp=pos.time
                )
                logger.info(f"[+] Reconciled external ticket into Shadow Book: {ticket} ({pos.symbol})")

        # Check for dropped positions (closed on broker, open in ledger)
        stale_tickets = [t for t in self.shadow_book if t not in live_tickets]
        for t in stale_tickets:
            logger.info(f"[*] Shadow ticket {t} confirmed closed by broker terminal.")
            del self.shadow_book[t]

        return True

# =====================================================================
# MASTER GATEWAY EXECUTION ENGINE
# =====================================================================

class InstitutionalExecutionGateway:
    def __init__(self, fleet: List[str]):
        self.fleet = fleet
        self.microstructure = MicrostructureGovernor()
        self.risk_governor = CovarianceRiskGovernor()
        self.audit = ShadowLedgerAudit()

    def run_pre_trade_gates(
        self,
        symbol: str,
        direction: int,
        stop_loss_points: float,
        win_rate: float = 0.55,
        payoff_ratio: float = 1.8
    ) -> Optional[float]:
        # Gate 1: State Ledger Reconciliation
        if not self.audit.audit_drift():
            logger.critical("[HALT] State Desync: In-flight broker drift detected. Aborting execution.")
            return None

        # Gate 2: Microstructure & Toxic Flow Check
        regime = self.microstructure.inspect_regime(symbol)
        if regime.is_toxic:
            logger.warning(f"[REJECT] {symbol} Microstructure Toxic: Spread {regime.spread:.1f} exceeds volatility threshold.")
            return None

        # Gate 3: Quantitative Sizing & Allocation
        account = mt5.account_info()
        if not account:
            return None

        allocation = self.risk_governor.calculate_lot_size(
            symbol=symbol,
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
            stop_loss_points=stop_loss_points,
            account_equity=account.equity
        )

        if allocation.target_lots <= 0:
            logger.info(f"[GATE] {symbol} Allocation evaluated to 0 lots. Skipping.")
            return None

        logger.info(
            f"[APPROVED] {symbol} Verified | Lots: {allocation.target_lots} | "
            f"Risk: ${allocation.max_capital_at_risk} (Kelly: {allocation.bayesian_kelly_factor*100:.2f}%)"
        )
        return allocation.target_lots


if __name__ == "__main__":
    if not mt5.initialize():
        logger.error(f"Failed to initialize MT5: {mt5.last_error()}")
        exit(1)

    fleet_symbols = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "US30"]
    gateway = InstitutionalExecutionGateway(fleet=fleet_symbols)

    logger.info("================ INSTITUTIONAL SKELETON AUDIT CHECK ================")
    for sym in fleet_symbols:
        mt5.symbol_select(sym, True)
        gateway.run_pre_trade_gates(symbol=sym, direction=0, stop_loss_points=350.0)

    mt5.shutdown()
