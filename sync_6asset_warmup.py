import re
import time
from pathlib import Path
import MetaTrader5 as mt5

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
SIX_ASSETS = ["XAUUSD", "US30", "BTCUSD", "EURUSD", "USDCHF", "USDCAD"]

# 1. Patch microstructure_sentinel.py if it has a hardcoded 3-symbol list
sent_path = BASE_DIR / "microstructure_sentinel.py"
if sent_path.exists():
    code = sent_path.read_text(encoding="utf-8")
    orig = code
    code = re.sub(
        r'(["\']XAUUSD["\']\s*,\s*["\']US30["\']\s*,\s*["\']BTCUSD["\'])',
        '"XAUUSD", "US30", "BTCUSD", "EURUSD", "USDCHF", "USDCAD"',
        code,
    )
    code = re.sub(
        r'(["\']XAUUSD["\']\s*,\s*["\']BTCUSD["\']\s*,\s*["\']US30["\'])',
        '"XAUUSD", "US30", "BTCUSD", "EURUSD", "USDCHF", "USDCAD"',
        code,
    )
    if code != orig:
        sent_path.write_text(code, encoding="utf-8")
        print("[OK] Updated microstructure_sentinel.py to stream all 6 V4.4 assets.")
    else:
        print("[INFO] microstructure_sentinel.py symbol list checked.")

# 2. Warm up MT5 Market Watch & M15/H1/D1 rate caches for all 6 symbols
if mt5.initialize(path=TERMINAL, portable=False):
    for sym in SIX_ASSETS:
        mt5.symbol_select(sym, True)
        for tf in (mt5.TIMEFRAME_M15, mt5.TIMEFRAME_H1, mt5.TIMEFRAME_D1):
            mt5.copy_rates_from_pos(sym, tf, 0, 100)
        time.sleep(0.3)
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 80)
        print(f"[WARMUP] {sym:<8} -> {len(r) if r is not None else 0} M15 bars ready in MT5 cache")
    mt5.shutdown()
