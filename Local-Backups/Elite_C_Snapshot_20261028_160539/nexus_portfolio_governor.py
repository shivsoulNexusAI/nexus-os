"""
NEXUS PORTFOLIO GOVERNOR // DIRECTIONAL BETA & FACTOR EXPOSURE ENGINE
"""
import MetaTrader5 as mt5

USD_QUOTE_PAIRS = {"EURUSD": -1, "GBPUSD": -1, "XAUUSD": -1} # SELL = +USD, BUY = -USD
CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD"}
MAX_NET_USD_EXPOSURE = 2
MAX_CRYPTO_SLOTS = 1

def evaluate_portfolio_heat(proposed_symbol: str, proposed_direction: str):
    """
    Evaluates whether a proposed trade passes multi-asset correlation and factor limits.
    Returns (passed: bool, reason: str, metrics: dict)
    """
    if not mt5.initialize():
        return False, "MT5 connection failed", {}

    positions = mt5.positions_get()
    if not positions:
        return True, "Portfolio empty (0 open)", {"net_usd": 0, "crypto_open": 0}

    net_usd = 0
    crypto_count = 0

    for p in positions:
        sym = p.symbol
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)

        # Track Crypto cluster
        if sym in CRYPTO_SYMBOLS:
            crypto_count += 1

        # Track USD Factor loading
        if sym in USD_QUOTE_PAIRS:
            # For EURUSD: BUY = Short USD (-1), SELL = Long USD (+1)
            usd_dir = -1 if is_buy else 1
            net_usd += usd_dir

    # Proposed trade factor delta
    proposed_is_buy = (proposed_direction.upper() == "BUY")
    proposed_usd_impact = 0
    if proposed_symbol in USD_QUOTE_PAIRS:
        proposed_usd_impact = -1 if proposed_is_buy else 1

    projected_net_usd = net_usd + proposed_usd_impact

    # Rule 1: Crypto Covariance Lock
    if proposed_symbol in CRYPTO_SYMBOLS and crypto_count >= MAX_CRYPTO_SLOTS:
        return False, f"Crypto covariance lock: Slot occupied ({crypto_count}/{MAX_CRYPTO_SLOTS})", {
            "net_usd": net_usd, "crypto_open": crypto_count
        }

    # Rule 2: Net USD Exposure Cap
    if abs(projected_net_usd) > MAX_NET_USD_EXPOSURE:
        direction_str = "LONG" if projected_net_usd > 0 else "SHORT"
        return False, f"Net USD Exposure Cap hit ({direction_str} {abs(projected_net_usd)} > {MAX_NET_USD_EXPOSURE})", {
            "net_usd": net_usd, "projected_net_usd": projected_net_usd
        }

    return True, "Portfolio heat within limits", {
        "net_usd": projected_net_usd, "crypto_open": crypto_count + (1 if proposed_symbol in CRYPTO_SYMBOLS else 0)
    }
