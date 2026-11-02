"""
NEXUS DRAWDOWN SENTINEL // INTRADAY HIGH-WATERMARK (HWM) RISK PRESERVATION
"""
import os
import json
from datetime import datetime, timezone
import MetaTrader5 as mt5

STATE_FILE = "session_risk_state.json"
MAX_DAILY_DRAWDOWN_PCT = 0.025  # 2.5% Hard Lockout
DEFENSIVE_DRAWDOWN_PCT = 0.015  # 1.5% Half-Kelly Sizing

def load_or_init_state():
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    state = {
        "date": today_str,
        "session_open_equity": 0.0,
        "peak_equity_hwm": 0.0,
        "locked_out": False,
        "defensive_mode": False
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                loaded = json.load(f)
                if loaded.get("date") == today_str:
                    return loaded
        except Exception:
            pass

    # Fresh session initialization
    if mt5.initialize():
        acc = mt5.account_info()
        if acc:
            state["session_open_equity"] = acc.equity
            state["peak_equity_hwm"] = acc.equity
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)

    return state

def evaluate_intraday_risk_gate():
    """
    Evaluates current equity relative to session peak HWM.
    Returns: (can_execute: bool, kelly_multiplier: float, reason: str, metrics: dict)
    """
    if not mt5.initialize():
        return False, 0.0, "MT5 disconnected", {}

    acc = mt5.account_info()
    if not acc:
        return False, 0.0, "Unable to read MT5 account", {}

    current_equity = acc.equity
    state = load_or_init_state()

    # Update Peak HWM if current equity pushed higher
    if current_equity > state.get("peak_equity_hwm", 0.0):
        state["peak_equity_hwm"] = current_equity
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    hwm = state.get("peak_equity_hwm", current_equity)
    if hwm <= 0:
        hwm = current_equity

    drawdown_usd = hwm - current_equity
    drawdown_pct = (drawdown_usd / hwm) if hwm > 0 else 0.0

    metrics = {
        "current_equity": current_equity,
        "peak_hwm": hwm,
        "drawdown_usd": round(drawdown_usd, 2),
        "drawdown_pct": round(drawdown_pct * 100, 2),
        "defensive": state.get("defensive_mode", False),
        "locked_out": state.get("locked_out", False)
    }

    # Hard Circuit Breaker (Tier 2: >= 2.5% DD)
    if drawdown_pct >= MAX_DAILY_DRAWDOWN_PCT:
        state["locked_out"] = True
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        return False, 0.0, f"DAILY CIRCUIT BREAKER: HWM DD {metrics['drawdown_pct']}% exceeds 2.5% max loss limit", metrics

    # Defensive Sizing (Tier 1: >= 1.5% DD)
    if drawdown_pct >= DEFENSIVE_DRAWDOWN_PCT:
        state["defensive_mode"] = True
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        return True, 0.50, f"DEFENSIVE MODE: HWM DD {metrics['drawdown_pct']}% (Sizing throttled 50%)", metrics

    # Clear defensive mode if equity recovered
    if state.get("defensive_mode", False) and drawdown_pct < DEFENSIVE_DRAWDOWN_PCT:
        state["defensive_mode"] = False
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    return True, 1.0, "Risk parameters healthy", metrics
