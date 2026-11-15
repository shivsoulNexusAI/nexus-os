# -*- coding: utf-8 -*-
"""
QUANT-NEXUS ML FEATURE PIPELINE (ROBUST IO)
Extracts 30 days of M5 bars, computes volatility dynamics,
and exports directly to CSV.GZ / Parquet.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
CSV_OUT = Path(r"C:\Quant-Nexus-Eng\ml_regime_dataset.csv.gz")
PARQUET_OUT = Path(r"C:\Quant-Nexus-Eng\ml_regime_dataset.parquet")
SYMBOLS = ["BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"]
BAR_COUNT = 8640  # ~30 days of M5 bars (288 bars/day * 30)

def extract_features():
    print("=" * 80)
    print("      EXTRACTING 30-DAY M5 BARS & COMPUTING REGIME FEATURES")
    print("=" * 80)
    
    if not mt5.initialize(path=TERMINAL, portable=False):
        print(f"[-] MT5 initialization failed: {mt5.last_error()}")
        sys.exit(1)

    all_dfs = []

    for sym in SYMBOLS:
        sym_info = mt5.symbol_info(sym)
        if not sym_info or not sym_info.visible:
            mt5.symbol_select(sym, True)

        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, BAR_COUNT)
        if rates is None or len(rates) < 200:
            print(f"[!] Warning: Only {0 if rates is None else len(rates)} bars for {sym}. Skipping.")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)

        o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["tick_volume"]

        # 1. True Range & Normalized ATR
        prev_c = c.shift(1)
        tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
        atr14 = tr.rolling(window=14).mean()
        df["natr14"] = (atr14 / c) * 100.0

        # ATR Expansion Ratio (current ATR14 vs rolling 6-hour baseline)
        rolling_baseline = tr.rolling(window=72).mean()
        df["atr_expansion_ratio"] = atr14 / rolling_baseline.replace(0, np.nan)

        # 2. Parkinson Volatility
        log_hl = np.log(h / l) ** 2
        df["parkinson_vol"] = np.sqrt((1.0 / (4.0 * np.log(2.0))) * log_hl.rolling(14).mean()) * np.sqrt(288 * 365)

        # 3. Garman-Klass Volatility
        log_co = np.log(c / o) ** 2
        gk_term = 0.5 * log_hl - (2.0 * np.log(2.0) - 1.0) * log_co
        df["garman_klass_vol"] = np.sqrt(np.maximum(0, gk_term.rolling(14).mean())) * np.sqrt(288 * 365)

        # 4. Candlestick Anatomy
        bar_range = np.maximum(h - l, 1e-6)
        df["upper_wick_ratio"] = (h - np.maximum(o, c)) / bar_range
        df["lower_wick_ratio"] = (np.minimum(o, c) - l) / bar_range
        df["body_ratio"] = (c - o).abs() / bar_range

        # 5. Relative Tick Volume
        df["rvol"] = v / v.rolling(window=24).mean().replace(0, np.nan)

        # 6. Returns
        df["ret_1"] = c.pct_change(1)
        df["ret_3"] = c.pct_change(3)
        df["ret_12"] = c.pct_change(12)

        # 7. Asset Encoding
        df["is_btc"] = 1 if sym == "BTCUSD" else 0
        df["is_gold"] = 1 if sym == "XAUUSD" else 0
        df["is_us30"] = 1 if sym == "US30" else 0

        # 8. Target Formulation (+1.5R expansion before -1.0R adverse move over 12 bars)
        target = []
        c_vals, h_vals, l_vals, atr_vals = c.values, h.values, l.values, atr14.values
        n_bars = len(df)
        horizon = 12

        for i in range(n_bars):
            if i + horizon >= n_bars or np.isnan(atr_vals[i]) or atr_vals[i] <= 0:
                target.append(np.nan)
                continue

            entry_p = c_vals[i]
            cur_atr = atr_vals[i]
            up_tp, up_sl = entry_p + (1.5 * cur_atr), entry_p - (1.0 * cur_atr)
            dn_tp, dn_sl = entry_p - (1.5 * cur_atr), entry_p + (1.0 * cur_atr)

            sub_h = h_vals[i + 1 : i + 1 + horizon]
            sub_l = l_vals[i + 1 : i + 1 + horizon]

            long_tp_idx = np.where(sub_h >= up_tp)[0]
            long_sl_idx = np.where(sub_l <= up_sl)[0]
            first_long_tp = long_tp_idx[0] if len(long_tp_idx) > 0 else 999
            first_long_sl = long_sl_idx[0] if len(long_sl_idx) > 0 else 999
            long_win = first_long_tp < first_long_sl

            short_tp_idx = np.where(sub_l <= dn_tp)[0]
            short_sl_idx = np.where(sub_h >= dn_sl)[0]
            first_short_tp = short_tp_idx[0] if len(short_tp_idx) > 0 else 999
            first_short_sl = short_sl_idx[0] if len(short_sl_idx) > 0 else 999
            short_win = first_short_tp < first_short_sl

            target.append(1 if (long_win or short_win) else 0)

        df["target_expansion"] = target
        df["symbol"] = sym

        clean = df.dropna().copy()
        print(f"[+] Processed {sym:<7}: {len(clean):>5} samples | Expansion Rate: {clean['target_expansion'].mean()*100:.1f}%")
        all_dfs.append(clean)

    mt5.shutdown()

    if not all_dfs:
        print("[-] Error: No data collected.")
        sys.exit(1)

    full_dataset = pd.concat(all_dfs, ignore_index=True)
    full_dataset.to_csv(CSV_OUT, index=False, compression="gzip")
    print(f"[+] Successfully saved compressed CSV: {CSV_OUT} ({len(full_dataset)} total rows)")

    try:
        full_dataset.to_parquet(PARQUET_OUT, index=False)
        print(f"[+] Also saved Parquet: {PARQUET_OUT}")
    except Exception as e:
        print(f"[i] Parquet export skipped ({e}). CSV.GZ ready for training.")

    print("=" * 80)

if __name__ == "__main__":
    extract_features()