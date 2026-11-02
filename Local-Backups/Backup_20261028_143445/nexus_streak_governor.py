"""
NEXUS STREAK GOVERNOR // MARKOV ASSET COOLDOWN & ANTI-MARTINGALE DECAY
"""
import time
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

QUARANTINE_SECONDS = 14400  # 4 Hours Lockout after 2 consecutive stop-outs
LOOKBACK_HOURS = 24

def evaluate_streak_gate(symbol: str):
    """
    Evaluates rolling trade history for a specific symbol.
    Returns: (passed: bool, sizing_multiplier: float, reason: str, metrics: dict)
    """
    if not mt5.initialize():
        return False, 0.0, "MT5 disconnected", {}

    now = datetime.now(timezone.utc)
    from_date = now - timedelta(hours=LOOKBACK_HOURS)

    deals = mt5.history_deals_get(from_date, now)
    if not deals:
        return True, 1.0, "No recent deal history for symbol", {"consecutive_losses": 0}

    # Filter closing deals for this symbol
    symbol_deals = [
        d for d in deals 
        if d.symbol == symbol and d.entry == mt5.DEAL_ENTRY_OUT and d.magic in [777901, 777902, 999999, 0]
    ]

    if not symbol_deals:
        return True, 1.0, "Clean record in 24h window", {"consecutive_losses": 0}

    # Sort descending by close time
    symbol_deals.sort(key=lambda x: x.time, reverse=True)

    consecutive_losses = 0
    last_loss_time = 0

    for d in symbol_deals:
        profit = d.profit + d.swap + d.commission
        if profit < 0:
            consecutive_losses += 1
            if last_loss_time == 0:
                last_loss_time = d.time
        else:
            break  # Streak broken by a profitable deal

    now_ts = int(time.time())
    elapsed_since_loss = now_ts - last_loss_time if last_loss_time > 0 else 999999

    metrics = {
        "symbol": symbol,
        "consecutive_losses": consecutive_losses,
        "last_loss_time": last_loss_time,
        "elapsed_seconds": elapsed_since_loss
    }

    # Condition 1: 2 or more consecutive losses -> Quarantine Lockout
    if consecutive_losses >= 2:
        if elapsed_since_loss < QUARANTINE_SECONDS:
            remaining_mins = round((QUARANTINE_SECONDS - elapsed_since_loss) / 60)
            return False, 0.0, f"Asset quarantined: {consecutive_losses} consecutive stop-outs. Lockout remaining: {remaining_mins}m", metrics
        else:
            # Quarantine expired, allow reentry with half sizing
            return True, 0.50, f"Quarantine expired ({consecutive_losses} past losses). Cautious reentry (50% sizing)", metrics

    # Condition 2: Exactly 1 loss -> Soft defensive sizing
    if consecutive_losses == 1:
        return True, 0.50, "Prior trade stopped out. Applying 50% anti-martingale sizing reduction", metrics

    return True, 1.0, "Streak healthy (No recent stop-outs)", metrics
