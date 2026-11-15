"""
QuantNexus V3.1 - Cross-Asset SMT Divergence Engine
"""
import MetaTrader5 as mt5

def check_smt_divergence(symbol_a="XAUUSD", symbol_b="USDJPY"):
    """
    Detects smart money technique (SMT) divergence across correlated instruments.
    """
    rates_a = mt5.copy_rates_from_pos(symbol_a, mt5.TIMEFRAME_M5, 0, 3)
    rates_b = mt5.copy_rates_from_pos(symbol_b, mt5.TIMEFRAME_M5, 0, 3)

    if rates_a is None or rates_b is None or len(rates_a) < 3 or len(rates_b) < 3:
        return False

    high_a_new = rates_a['high'][-1] > rates_a['high'][-2]
    high_b_new = rates_b['high'][-1] > rates_b['high'][-2]

    low_a_new = rates_a['low'][-1] < rates_a['low'][-2]
    low_b_new = rates_b['low'][-1] < rates_b['low'][-2]

    bullish_smt = low_a_new and not low_b_new
    bearish_smt = high_a_new and not high_b_new

    return bullish_smt or bearish_smt
