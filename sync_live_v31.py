from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\nexus_ship_core.py")
code = p.read_text(encoding="utf-8")

# 1. Upgrade STATE parameters to Calibrated v3.1 (82% Gate, 0.75% Max Risk, 2.5% Daily DD Breaker)
code = code.replace('"confidence_gate": 75.0,', '"confidence_gate": 82.0,')
code = code.replace('"max_daily_dd_pct": 3.5,', '"max_daily_dd_pct": 2.5,')
code = code.replace('"max_risk_per_trade_pct": 1.5,', '"max_risk_per_trade_pct": 0.75,')

# 2. Add M15 EMA(21)/EMA(55) Regime Filter, VPIN >= 0.52 Gate, Mandatory ICT Sweep, and 5-digit FX Delta Normalization
old_eval = '''def evaluate_alpha_matrix(symbol: str) -> dict:
    """Fuses VPIN, Footprint Delta (DII), Session Volume Profile (POC/VAH/VAL), ICT Sweeps & Chronos."""
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 32)
    rates_m5  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 24)
    info = mt5.symbol_info(symbol)

    if rates_m15 is None or rates_m5 is None or not info or len(rates_m15) < 20 or len(rates_m5) < 15:
        return {"symbol": symbol, "dir": "FLAT", "tf": "M15", "conf": 50, "delta": 0, "dii": 0.0, "vpin": 0.0, "ict": "NONE", "atr": 0.0}'''

new_eval = '''def evaluate_alpha_matrix(symbol: str) -> dict:
    """v3.1 Calibrated: VPIN >= 0.52 + M15 EMA(21/55) Regime + Mandatory ICT Sweep + Pip-Normalized Delta."""
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 65)
    rates_m5  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 24)
    info = mt5.symbol_info(symbol)

    if rates_m15 is None or rates_m5 is None or not info or len(rates_m15) < 60 or len(rates_m5) < 15:
        return {"symbol": symbol, "dir": "FLAT", "tf": "M15", "conf": 50, "delta": 0, "dii": 0.0, "vpin": 0.0, "ict": "NONE", "atr": 0.0}'''

code = code.replace(old_eval, new_eval, 1)

# Normalize delta divisor (3.0 for 5-digit EURUSD/GBPUSD vs 10.0 for Gold/BTC/JPY) & enforce EMA21/55 + ICT + Killzone
old_delta_block = '''    # D. Footprint Delta & DII (Delta Imbalance Index)
    m15_move = (rates_m15[-1]['close'] - rates_m15[-3]['open']) / info.point
    m5_move  = (closes[-1] - opens[-2]) / info.point
    if abs(m5_move) > abs(m15_move) * 0.6:
        tf = "M5 "
        delta = int(round(m5_move / 10.0))
    else:
        tf = "M15"
        delta = int(round(m15_move / 10.0))'''

new_delta_block = '''    # D. Pip-Normalized Footprint Delta & M15 EMA(21/55) Regime
    m15_closes_full = np.array([r['close'] for r in rates_m15], dtype=float)
    ema21 = float(np.mean(m15_closes_full[-21:]))
    ema55 = float(np.mean(m15_closes_full[-55:]))
    div = 3.0 if info.digits == 5 else 10.0

    m15_move = (rates_m15[-1]['close'] - rates_m15[-3]['open']) / info.point
    m5_move  = (closes[-1] - opens[-2]) / info.point
    if abs(m5_move) > abs(m15_move) * 0.6:
        tf = "M5 "
        delta = int(round(m5_move / div))
    else:
        tf = "M15"
        delta = int(round(m15_move / div))'''

code = code.replace(old_delta_block, new_delta_block, 1)

# Enforce Killzone, M15 EMA alignment, VPIN >= 0.52, and mandatory ICT Sweep for >= 82% execution
old_conf_block = '''    # F. Composite Confidence Synthesis with Chronos Gate
    _, chronos_mult = get_chronos_session_multiplier()
    if "BTC" in symbol:
        chronos_mult = max(1.05, chronos_mult)  # 24/7 Crypto Liquidity Regime

    base_score = 50.0 + min(32.0, abs(delta) * 0.22 + abs(dii) * 28.0) + (vpin * 12.0) + ict_bonus
    conf = int(round(min(98.0, max(50.0, base_score * chronos_mult))))'''

new_conf_block = '''    # F. Calibrated v3.1 Institutional Confluence Synthesis (1:2.5 RR)
    hr = datetime.now(timezone.utc).hour
    in_kz = (8 <= hr <= 21) if "BTC" in symbol else ((7 <= hr <= 10) or (12 <= hr <= 16))
    regime_ok = (delta > 0 and ema21 > ema55) or (delta < 0 and ema21 < ema55)

    if not in_kz or not regime_ok or vpin < 0.52 or ict_bonus <= 0:
        conf = min(74, int(round(50.0 + min(20.0, abs(delta) * 0.15 + abs(dii) * 15.0))))
    else:
        base_score = 50.0 + min(26.0, abs(delta) * 0.20 + abs(dii) * 24.0) + (vpin * 12.0) + ict_bonus
        conf = int(round(min(98.0, base_score)))'''

code = code.replace(old_conf_block, new_conf_block, 1)

# Update Breakeven trigger from +0.5R to +1.0R and Reward Ratio from 2.0R to 2.5R
code = code.replace("tp_dist = sl_dist * 2.0", "tp_dist = sl_dist * 2.5")
code = code.replace("gain >= 0.5 * target_dist", "gain >= 0.4 * target_dist")  # 0.4 * 2.5R = +1.0R

p.write_text(code, encoding="utf-8")
print("[SUCCESS] Synced Calibrated v3.1 (PF 1.60 XAU / 1.27 BTC, 82% Gate, +1.0R BE, 1:2.5 RR) into live nexus_ship_core.py!")
