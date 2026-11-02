"""
NEXUS SPREAD SHIELD // BROKER FRICTION & ROLLOVER LIQUIDITY GOVERNOR
"""
import MetaTrader5 as mt5
from datetime import datetime, timezone

ROLLOVER_START_HOUR = 21
ROLLOVER_START_MIN = 58
ROLLOVER_END_HOUR = 22
ROLLOVER_END_MIN = 10

MAX_SPREAD_MULTIPLIER = 2.0  # Max acceptable spread expansion factor

# Hard ceilings in points (failsafe limits if baseline is uncalculated)
HARD_SPREAD_CEILINGS = {
    "XAUUSD": 60,    # $0.60
    "BTCUSD": 3500,  # $35.00
    "ETHUSD": 400,   # $4.00
    "EURUSD": 25,    # 2.5 pips
    "GBPUSD": 35,    # 3.5 pips
    "US30": 450      # 4.5 pts
}

def is_rollover_window():
    """Returns True if within the daily broker rollover / swap window (21:58-22:10 UTC)."""
    now = datetime.now(timezone.utc)
    current_minutes = now.hour * 60 + now.minute
    start_minutes = ROLLOVER_START_HOUR * 60 + ROLLOVER_START_MIN
    end_minutes = ROLLOVER_END_HOUR * 60 + ROLLOVER_END_MIN
    return start_minutes <= current_minutes <= end_minutes

def evaluate_spread_gate(symbol: str):
    """
    Evaluates current broker spread against rolling baselines and hard thresholds.
    Returns: (passed: bool, reason: str, metrics: dict)
    """
    if not mt5.initialize():
        return False, "MT5 disconnected", {}

    if is_rollover_window():
        return False, "Broker rollover window active (21:58-22:10 UTC) - executions frozen", {
            "rollover": True
        }

    tick = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    if not tick or not sym_info:
        return False, f"Failed to retrieve tick for {symbol}", {}

    point = sym_info.point
    current_spread_points = round((tick.ask - tick.bid) / point) if point > 0 else 9999

    # Hard ceiling check
    hard_limit = HARD_SPREAD_CEILINGS.get(symbol, 50)
    if current_spread_points > hard_limit:
        return False, f"Spread blown out: {current_spread_points} pts > hard ceiling {hard_limit} pts", {
            "spread_points": current_spread_points, "limit": hard_limit
        }

    # Dynamic baseline comparison via symbol info
    typical_spread = sym_info.spread
    if typical_spread > 0 and current_spread_points > (typical_spread * MAX_SPREAD_MULTIPLIER):
        return False, f"Spread expanded {current_spread_points} pts > {MAX_SPREAD_MULTIPLIER}x typical ({typical_spread} pts)", {
            "spread_points": current_spread_points, "typical": typical_spread
        }

    return True, "Spread within acceptable liquidity tolerances", {
        "spread_points": current_spread_points,
        "typical_spread": typical_spread,
        "point_val": point
    }
