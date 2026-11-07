"""
QUANT NEXUS SOVEREIGN RISK KERNEL (v3.0)
Single source of truth for dynamic Kelly sizing, portfolio drawdown governance,
and non-blocking Telegram telemetry across all execution engines.
"""
import os
import json
import time
import logging
from datetime import datetime, timezone
import MetaTrader5 as mt5

try:
    from nexus_telegram import send_alert
except ImportError:
    def send_alert(role, msg): logging.info(f"[{role}] {msg}")

STATE_FILE = r"C:\Quant-Nexus-Eng\risk_state.json"

class NexusRiskKernel:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(NexusRiskKernel, cls).__new__(cls)
            cls._instance._init_kernel()
        return cls._instance

    def _init_kernel(self):
        self.max_daily_dd_pct = 0.05    # 5% Max Daily Drawdown lockout
        self.defensive_dd_pct = 0.025   # 2.5% Half-Kelly throttle
        self.kelly_fraction   = 0.25    # Quarter-Kelly baseline
        self.min_risk_pct     = 0.0025  # 0.25% equity floor
        self.max_risk_pct     = 0.02    # 2.0% equity ceiling
        self.load_state()

    def load_state(self):
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                if self.state.get("date") != today_str:
                    self._reset_daily_state(today_str)
            except Exception:
                self._reset_daily_state(today_str)
        else:
            self._reset_daily_state(today_str)

    def _reset_daily_state(self, date_str):
        self.state = {
            "date": date_str,
            "starting_balance": 0.0,
            "peak_equity_hwm": 0.0,
            "circuit_breaker_tripped": False,
            "lockout_reason": "",
            "last_updated": time.time()
        }
        self.save_state()

    def save_state(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logging.error(f"[RISK-KERNEL-IO-ERR] {e}")

    def audit_governance(self) -> tuple[bool, str, dict]:
        """Audits current MT5 account equity against high-watermark boundaries."""
        acc = mt5.account_info()
        if not acc:
            return False, "MT5 Account Disconnected", {}

        eq = acc.equity
        bal = acc.balance
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if self.state.get("date") != today_str:
            self._reset_daily_state(today_str)

        if self.state["starting_balance"] <= 0.0:
            self.state["starting_balance"] = bal
            self.state["peak_equity_hwm"] = max(bal, eq)

        if eq > self.state["peak_equity_hwm"]:
            self.state["peak_equity_hwm"] = eq

        hwm = self.state["peak_equity_hwm"]
        drawdown_pct = (hwm - eq) / hwm if hwm > 0 else 0.0

        if drawdown_pct >= self.max_daily_dd_pct:
            if not self.state["circuit_breaker_tripped"]:
                self.state["circuit_breaker_tripped"] = True
                self.state["lockout_reason"] = f"Hard 5% DD breach (-{drawdown_pct*100:.2f}%)"
                send_alert("quant_alert_bot", f"🚨 <b>CIRCUIT BREAKER LATCHED</b>\nNAV: ${eq:,.2f} | HWM: ${hwm:,.2f}\nDrawdown: {drawdown_pct*100:.2f}% (Limit: 5%)")
            self.save_state()
            return False, self.state["lockout_reason"], {"regime": "LOCKED", "equity": eq, "hwm": hwm}

        regime = "DEFENSIVE" if drawdown_pct >= self.defensive_dd_pct else "OPTIMAL"
        self.save_state()
        return True, "CLEAR", {"regime": regime, "equity": eq, "hwm": hwm, "dd_pct": drawdown_pct}

    def compute_position_size(self, symbol: str, stop_loss_points: float, edge: float = 0.55, payoff: float = 1.6) -> float:
        """Calculates dynamic lot sizing via Fractional Kelly scaled to account equity."""
        allowed, reason, metrics = self.audit_governance()
        if not allowed or stop_loss_points <= 0:
            return 0.0

        acc = mt5.account_info()
        info = mt5.symbol_info(symbol)
        if not acc or not info:
            return 0.0

        # Kelly formulation: f* = (p*b - q) / b
        p = max(0.40, min(edge, 0.85))
        b = max(1.0, payoff)
        q = 1.0 - p
        raw_kelly = (p * b - q) / b

        multiplier = self.kelly_fraction
        if metrics.get("regime") == "DEFENSIVE":
            multiplier *= 0.50

        allocated_pct = max(self.min_risk_pct, min(self.max_risk_pct, raw_kelly * multiplier))
        risk_cash = acc.equity * allocated_pct

        tick_val = info.trade_tick_value if info.trade_tick_value > 0 else 1.0
        tick_size = info.trade_tick_size if info.trade_tick_size > 0 else info.point
        point_loss_per_lot = (info.point / tick_size) * tick_val

        lot_step = info.volume_step if info.volume_step > 0 else 0.01
        raw_lots = risk_cash / (stop_loss_points * point_loss_per_lot)

        lots = round(raw_lots / lot_step) * lot_step
        lots = max(info.volume_min, min(info.volume_max, lots))
        return round(lots, 2)

risk_kernel = NexusRiskKernel()