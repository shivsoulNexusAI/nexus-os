import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

# Asset Correlation Clusters
CORRELATION_CLUSTERS = {
    'CRYPTO': ['BTCUSD', 'ETHUSD'],
    'METALS': ['XAUUSD'],
    'FOREX': ['EURUSD', 'GBPUSD', 'USDJPY']
}

MAX_CONSECUTIVE_LOSSES = 2
MAX_DAILY_LOSS_PCT = 0.05

def is_cluster_locked(target_symbol):
    """Returns True if another symbol in the same correlated cluster is already open."""
    positions = mt5.positions_get()
    if not positions:
        return False
        
    target_cluster = None
    for cluster, symbols in CORRELATION_CLUSTERS.items():
        if target_symbol in symbols:
            target_cluster = cluster
            break
            
    if not target_cluster:
        return False

    for pos in positions:
        if pos.symbol in CORRELATION_CLUSTERS.get(target_cluster, []) and pos.symbol != target_symbol:
            return True
    return False

def check_circuit_breaker():
    """Checks daily loss ceiling and consecutive stop-out thresholds."""
    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    
    deals = mt5.history_deals_get(day_start, now)
    if not deals:
        return True, "CLEAN"
        
    closed_deals = [d for d in deals if d.entry == 1]
    
    consecutive_losses = 0
    for d in reversed(closed_deals):
        if d.profit < 0:
            consecutive_losses += 1
        elif d.profit > 0:
            break
            
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return False, f"CIRCUIT_BREAKER: {consecutive_losses} consecutive losses. Cooldown active."
        
    return True, "CLEAN"
