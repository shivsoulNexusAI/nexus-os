import MetaTrader5 as mt5

def check_execution_spread_safety(symbol: str, max_spread_points: float = None) -> dict:
    """
    Evaluates whether real-time bid-ask spread is within safe operational thresholds.
    Prevents execution during rollover widening or unexpected liquidity gaps.
    """
    tick = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)

    if not tick or not sym_info:
        return {"safe_to_execute": False, "reason": "TICK_FEED_UNAVAILABLE", "current_spread": 0}

    point = sym_info.point
    current_spread_points = round((tick.ask - tick.bid) / point, 1)

    # Dynamic default thresholds based on asset class
    if max_spread_points is None:
        if "XAU" in symbol:
            max_allowed = 45.0   # $0.45 gold spread threshold
        elif "BTC" in symbol:
            max_allowed = 350.0  # Crypto volatility threshold
        else:
            max_allowed = 25.0   # FX pairs (2.5 pips max)
    else:
        max_allowed = max_spread_points

    if current_spread_points > max_allowed:
        return {
            "safe_to_execute": False,
            "reason": f"SPREAD_SPIKE_DETECTED ({current_spread_points} > {max_allowed} pts)",
            "current_spread": current_spread_points,
            "max_allowed": max_allowed
        }

    return {
        "safe_to_execute": True,
        "reason": "OPTIMAL_LIQUIDITY",
        "current_spread": current_spread_points,
        "max_allowed": max_allowed
    }
