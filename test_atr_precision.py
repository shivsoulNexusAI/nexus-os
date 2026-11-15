import MetaTrader5 as mt5
import pandas as pd
import numpy as np

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
SYMBOLS = ["BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"]

if mt5.initialize(path=TERMINAL, portable=False):
    print("=" * 85)
    print("RAW UNROUNDED ATR & BUFFER ANALYSIS")
    print("=" * 85)
    for sym in SYMBOLS:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 100)
        info = mt5.symbol_info(sym)
        if rates is None or info is None:
            continue
        df = pd.DataFrame(rates)
        h, l, c = df["high"], df["low"], df["close"]
        prev_c = c.shift(1)
        tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        
        atr_in_pips = atr14 / info.point
        k_buf = 1.2
        buf_dist = max(atr14 * k_buf, info.spread * info.point * 2.0)
        
        print(f"{sym:<7} | Digits: {info.digits} | Point: {info.point:.5f} | Raw ATR14: {atr14:.6f} ({atr_in_pips:5.1f} pts) | BufDist: {buf_dist:.6f}")
    mt5.shutdown()
    print("=" * 85)