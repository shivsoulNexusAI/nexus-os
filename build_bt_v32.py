from pathlib import Path

src = Path(r"C:\Quant-Nexus-Eng\backtest_v31_calibrated.py")
dst = Path(r"C:\Quant-Nexus-Eng\backtest_v32_calibrated.py")
code = src.read_text(encoding="utf-8")

# 1. Extend microstructure VPOC/Delta gating to all 6 symbols
code = code.replace(
    'MICRO_GATED = {"XAUUSD", "BTCUSD"}',
    'MICRO_GATED = {"BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"}'
)

# 2. Restrict DII fades strictly to XAUUSD & BTCUSD VAH bearish exhaustion (block VAL bullish knife-catching)
code = code.replace(
    'FADE_SYMBOLS = {"XAUUSD", "BTCUSD", "EURUSD"}',
    'FADE_SYMBOLS = {"XAUUSD", "BTCUSD"}'
)

# 3. Raise EURUSD & GBPUSD ML regime hurdle from 0.65 -> 0.70
code = code.replace('"EURUSD": 0.65,', '"EURUSD": 0.70,')
code = code.replace('"GBPUSD": 0.65,', '"GBPUSD": 0.70,')

# 4. Align V3.2 bracket geometry (k_buf=1.1, k_sl=1.1, k_tp=2.8)
code = code.replace(
    'sl_d = atr * 1.2 if upgraded else atr * 0.8',
    'sl_d = atr * 1.1 if upgraded else atr * 0.8'
)

# 5. Disable bullish VAL DII fade in V3.2 (keep bearish VAH exhaustion fade only)
old_bull_fade = """                if dii >= 2.5 and close_p >= prev_c and close_p <= val:"""
new_bull_fade = """                if False and dii >= 2.5 and close_p >= prev_c and close_p <= val:"""
assert old_bull_fade in code, "Bull fade block not found"
code = code.replace(old_bull_fade, new_bull_fade, 1)

# 6. Update report path and label
code = code.replace(
    'OUT_REPORT = Path(r"C:\\Quant-Nexus-Eng\\backtest_calibrated_2025_2026.json")',
    'OUT_REPORT = Path(r"C:\\Quant-Nexus-Eng\\backtest_v32_2025_2026.json")'
)
code = code.replace(
    '"V3.1_CALIBRATED (Killzone + VPOC/Delta + DII Fade + 1.2x ATR SL)"',
    '"V3.2_CALIBRATED (6-Sym Micro + 0.70 FX Hurdle + Bearish VAH Fade + 1.1x ATR SL)"'
)

dst.write_text(code, encoding="utf-8")
print("[OK] Generated backtest_v32_calibrated.py")