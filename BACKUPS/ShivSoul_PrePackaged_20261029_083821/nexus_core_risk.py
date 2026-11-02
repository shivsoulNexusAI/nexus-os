import json
import os
import datetime
from datetime import timezone, timedelta
import numpy as np
import MetaTrader5 as mt5

STATE_FILE = "circuit_breaker_state.json"

# Bayesian Kelly Prior Hyperparameters (from nexus_bayesian_kelly.py)
PRIOR_ALPHA = 12.0   # 12 prior wins
PRIOR_BETA = 8.0     # 8 prior losses -> 60% baseline prior win rate
DECAY_LAMBDA = 0.96  # Exponential regime memory decay (~25 trades)

class DynamicNexusRisk:
    def __init__(
        self,
        max_dd_pct: float = 0.05,
        emergency_floor_pct: float = 0.10,
        kelly_fraction: float = 0.25,
        min_risk_pct: float = 0.0025,
        max_risk_pct: float = 0.02,
        single_trade_risk_pct: float = None  # Tolerates legacy calls
    ):
        self.max_dd_pct = float(max_dd_pct)
        self.emergency_floor_pct = float(emergency_floor_pct)
        self.kelly_fraction = float(kelly_fraction)
        self.min_risk_pct = float(min_risk_pct)
        self.max_risk_pct = float(max_risk_pct)
        if single_trade_risk_pct is not None:
            self.baseline_risk = float(single_trade_risk_pct)
        else:
            self.baseline_risk = 0.01  # Default 1% baseline prior
            
        self.state_file = STATE_FILE
        self._ensure_calibrated()

    def get_live_metrics(self):
        acc = mt5.account_info()
        if not acc:
            return None
        return {
            "login": acc.login,
            "server": acc.server,
            "balance": acc.balance,
            "equity": acc.equity,
            "leverage": acc.leverage,
            "margin_free": acc.margin_free
        }

    def _ensure_calibrated(self):
        metrics = self.get_live_metrics()
        equity = metrics["equity"] if metrics else 10000.0

        if not os.path.exists(self.state_file):
            self.reset_state(equity)
            return

        try:
            with open(self.state_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            hwm = data.get("high_water_mark", 0.0)
            if hwm <= 0 or abs(equity - hwm) / max(hwm, 1.0) > 0.50:
                self.reset_state(equity)
        except Exception:
            self.reset_state(equity)

    def reset_state(self, equity: float):
        state = {
            "high_water_mark": round(equity, 2),
            "current_floor": round(equity * (1.0 - self.max_dd_pct), 2),
            "base_floor": round(equity * (1.0 - self.emergency_floor_pct), 2),
            "max_drawdown_pct": self.max_dd_pct,
            "is_tripped": False,
            "tripped_timestamp": None,
            "last_updated_utc": datetime.datetime.now(timezone.utc).isoformat()
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
        return state

    def evaluate(self):
        metrics = self.get_live_metrics()
        if not metrics:
            return {"allowed": False, "reason": "MT5 Connection Offline"}

        equity = metrics["equity"]

        with open(self.state_file, "r", encoding="utf-8-sig") as f:
            state = json.load(f)

        if state.get("is_tripped", False):
            return {
                "allowed": False,
                "reason": f"LATCHED since {state.get('tripped_timestamp')}",
                "floor": state["current_floor"],
                "hwm": state["high_water_mark"]
            }

        # Dynamic high-water mark ratchet
        if equity > state["high_water_mark"]:
            state["high_water_mark"] = round(equity, 2)
            state["current_floor"] = round(equity * (1.0 - self.max_dd_pct), 2)
            state["last_updated_utc"] = datetime.datetime.now(timezone.utc).isoformat()
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)

        # Dynamic floor breach check
        if equity <= state["current_floor"]:
            state["is_tripped"] = True
            state["tripped_timestamp"] = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            state["last_updated_utc"] = datetime.datetime.now(timezone.utc).isoformat()
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
            return {
                "allowed": False,
                "reason": f"BREACHED Floor ${state['current_floor']:,.2f} (Live Equity: ${equity:,.2f})",
                "floor": state["current_floor"],
                "hwm": state["high_water_mark"]
            }

        buffer_usd = equity - state["current_floor"]
        return {
            "allowed": True,
            "equity": equity,
            "hwm": state["high_water_mark"],
            "floor": state["current_floor"],
            "buffer_usd": round(buffer_usd, 2)
        }

    def compute_bayesian_kelly_risk(self, lookback_days: int = 14) -> dict:
        """
        Online Bayesian posterior win probability with dynamic Quarter-Kelly allocation.
        """
        now = datetime.datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=lookback_days), now)

        out_deals = []
        if deals:
            out_deals = [
                d for d in deals
                if d.entry == mt5.DEAL_ENTRY_OUT and d.magic in [777901, 777902, 777903, 999999, 0]
            ]

        alpha = PRIOR_ALPHA
        beta = PRIOR_BETA
        wins = []
        losses = []

        if len(out_deals) >= 5:
            out_deals.sort(key=lambda x: x.time)
            for d in out_deals:
                pnl = d.profit + d.swap + d.commission
                if pnl > 0:
                    alpha = (DECAY_LAMBDA * alpha) + 1.0
                    beta = (DECAY_LAMBDA * beta)
                    wins.append(pnl)
                elif pnl < 0:
                    alpha = (DECAY_LAMBDA * alpha)
                    beta = (DECAY_LAMBDA * beta) + 1.0
                    losses.append(abs(pnl))

        # Posterior win probability: mean of Beta(alpha, beta)
        p_mean = alpha / (alpha + beta)
        
        # Payoff ratio b = avg_win / avg_loss
        avg_win = float(np.mean(wins)) if wins else 50.0
        avg_loss = float(np.mean(losses)) if losses else 30.0
        b = max(0.8, avg_win / max(avg_loss, 1.0))
        
        # Full Kelly formula: f* = (p * b - q) / b
        q_mean = 1.0 - p_mean
        raw_kelly = (p_mean * b - q_mean) / b if b > 0 else 0.0

        # Fractional Kelly sizing with institutional volatility clamps
        if raw_kelly <= 0:
            allocated_risk_pct = self.min_risk_pct
        else:
            allocated_risk_pct = min(self.max_risk_pct, max(self.min_risk_pct, raw_kelly * self.kelly_fraction))

        return {
            "deals_sampled": len(out_deals),
            "posterior_alpha": round(alpha, 2),
            "posterior_beta": round(beta, 2),
            "posterior_win_rate": round(p_mean, 4),
            "empirical_payoff_b": round(b, 3),
            "raw_kelly_f": round(raw_kelly, 4),
            "kelly_fraction": self.kelly_fraction,
            "allocated_risk_pct": round(allocated_risk_pct, 4)
        }

    def compute_dynamic_lot(self, symbol: str, sl_points: float) -> float:
        """
        Dynamically sizes order volume using the Bayesian Kelly Risk Fraction against live equity.
        """
        metrics = self.get_live_metrics()
        if not metrics or sl_points <= 0:
            return 0.01

        equity = metrics["equity"]
        kelly_data = self.compute_bayesian_kelly_risk()
        risk_pct = kelly_data["allocated_risk_pct"]
        risk_capital = equity * risk_pct

        info = mt5.symbol_info(symbol)
        if not info:
            return 0.01

        point = info.point
        tick_val = info.trade_tick_value or 1.0
        tick_size = info.trade_tick_size or point

        point_value = (tick_val / tick_size) * point
        loss_per_lot = sl_points * point_value

        if loss_per_lot <= 0:
            return info.volume_min

        raw_lot = risk_capital / loss_per_lot
        step = info.volume_step or 0.01
        lot = round(raw_lot / step) * step
        lot = max(info.volume_min, min(info.volume_max, lot))
        return round(lot, 2)