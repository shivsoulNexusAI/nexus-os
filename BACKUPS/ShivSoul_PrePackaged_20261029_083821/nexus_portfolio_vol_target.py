"""
NEXUS PORTFOLIO VOLATILITY TARGET GOVERNOR // ANNUALIZED RISK BUDGETING
"""
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ANNUAL_TARGET_VOL = 0.15      # 15.0% Annualized Portfolio Volatility Budget
MAX_PERMISSIBLE_VOL = 0.22    # 22.0% Hard Heat Ceiling (Veto Threshold)

# Baseline annualized volatility estimates (M15 annualized proxy)
ASSET_VOL_BASELINES = {
    "XAUUSD": 0.18,
    "BTCUSD": 0.55,
    "ETHUSD": 0.65,
    "EURUSD": 0.08,
    "GBPUSD": 0.10,
    "US30": 0.16
}

def calculate_asset_annual_vol(symbol: str) -> float:
    """Calculates annualized volatility using M15 log-returns."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 96) # 24 hours of M15
    if rates is None or len(rates) < 50:
        return ASSET_VOL_BASELINES.get(symbol, 0.18)
    
    closes = pd.Series([r[4] for r in rates])
    log_ret = np.log(closes / closes.shift(1)).dropna()
    std_m15 = log_ret.std()
    # 252 trading days * 24 hours * 4 fifteen-minute bars = 24,192 bars/year
    annual_vol = std_m15 * np.sqrt(24192)
    return float(np.clip(annual_vol, 0.05, 1.20))

def evaluate_portfolio_vol_budget(proposed_symbol: str, proposed_lots: float):
    """
    Evaluates aggregate annualized portfolio volatility if the proposed trade is added.
    Returns: (passed: bool, budget_multiplier: float, reason: str, metrics: dict)
    """
    if not mt5.initialize():
        return True, 1.0, "MT5 bypass", {}

    acc = mt5.account_info()
    if not acc or acc.equity <= 0:
        return True, 1.0, "Account info unavailable", {}

    equity = acc.equity
    positions = mt5.positions_get()

    exposures = []
    
    # 1. Calculate existing exposures
    if positions:
        for p in positions:
            sym_info = mt5.symbol_info(p.symbol)
            if not sym_info:
                continue
            contract_size = sym_info.trade_contract_size
            notional = p.volume * contract_size * p.price_open
            weight = notional / equity
            vol = calculate_asset_annual_vol(p.symbol)
            exposures.append({"symbol": p.symbol, "weight": weight, "vol": vol})

    # 2. Add proposed candidate exposure
    prop_sym_info = mt5.symbol_info(proposed_symbol)
    prop_tick = mt5.symbol_info_tick(proposed_symbol)
    if prop_sym_info and prop_tick:
        prop_price = prop_tick.ask
        prop_notional = proposed_lots * prop_sym_info.trade_contract_size * prop_price
        prop_weight = prop_notional / equity
        prop_vol = calculate_asset_annual_vol(proposed_symbol)
        exposures.append({"symbol": proposed_symbol, "weight": prop_weight, "vol": prop_vol})

    if not exposures:
        return True, 1.0, "Portfolio empty", {"projected_vol": 0.0}

    # 3. Compute portfolio variance proxy: sigma_port = sqrt(sum((w_i * vol_i)^2) + covariance_cross_term)
    # Using an institutional conservative average correlation factor rho = 0.30
    weights = np.array([e["weight"] for e in exposures])
    vols = np.array([e["vol"] for e in exposures])
    wv = weights * vols

    # Matrix formulation: w^T * Sigma * w
    n = len(wv)
    corr_matrix = np.full((n, n), 0.30)
    np.fill_diagonal(corr_matrix, 1.0)
    
    port_variance = np.dot(wv, np.dot(corr_matrix, wv))
    projected_port_vol = float(np.sqrt(max(0.0, port_variance)))

    metrics = {
        "projected_port_vol": round(projected_port_vol * 100, 2),
        "target_vol": round(ANNUAL_TARGET_VOL * 100, 2),
        "active_positions_count": len(exposures)
    }

    # Check against hard ceiling
    if projected_port_vol > MAX_PERMISSIBLE_VOL:
        return False, 0.0, f"Portfolio heat saturated: Projected Vol {projected_port_vol*100:.1f}% > {MAX_PERMISSIBLE_VOL*100:.0f}% ceiling", metrics

    # Compute budget scale factor
    if projected_port_vol > ANNUAL_TARGET_VOL:
        scalar = round(ANNUAL_TARGET_VOL / projected_port_vol, 2)
        return True, max(0.35, scalar), f"Vol budget throttling applied ({scalar*100:.0f}% sizing)", metrics

    return True, 1.0, "Portfolio volatility within optimal budget", metrics
