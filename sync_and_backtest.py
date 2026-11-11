import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

TERMINAL = r"C:/MT5_Quant_278017866/terminal64.exe"
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
END_DATE = datetime(2026, 11, 1, tzinfo=timezone.utc)
START_DATE = datetime(2025, 11, 1, tzinfo=timezone.utc)

if not mt5.initialize(path=TERMINAL, portable=False):
    print("[-] MT5 Init failed.")
    exit(1)

print("=" * 105)
print("1-YEAR QUANTITATIVE AUDIT & BACKTEST ENGINE (2025-11-01 to 2026-11-01)")
print("Synchronizing M5 Bar Repositories Across Exness Servers...")
print("=" * 105)

results = []

for sym in SYMBOLS:
    mt5.symbol_select(sym, True)
    
    # 1. Warm-up and force sync historical cache from broker
    mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, START_DATE, END_DATE)
    mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, START_DATE, END_DATE)
    
    # Fetch M5 bars in 30-day blocks to prevent broker payload throttling
    all_chunks = []
    cur_start = START_DATE
    while cur_start < END_DATE:
        cur_end = min(cur_start + timedelta(days=35), END_DATE)
        chunk = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, cur_start, cur_end)
        if chunk is not None and len(chunk) > 0:
            all_chunks.append(pd.DataFrame(chunk))
        cur_start = cur_end

    if not all_chunks:
        # Fallback to pos query if range is restricted by trial server
        rates_fallback = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 80000)
        if rates_fallback is not None and len(rates_fallback) > 500:
            df = pd.DataFrame(rates_fallback)
        else:
            print(f"[-] Could not sync historical M5 bars for {sym}")
            continue
    else:
        df = pd.concat(all_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

    df["time"] = pd.to_datetime(df["time"], unit="s")
    total_bars = len(df)
    first_date = df["time"].iloc[0].strftime("%Y-%m-%d")
    last_date = df["time"].iloc[-1].strftime("%Y-%m-%d")
    print(f"[+] {sym:<7} | Synchronized {total_bars:,} M5 bars ({first_date} -> {last_date})")

    # Metrics Computation
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
    df["atr14"] = tr.rolling(14).mean()
    df["atr_base"] = tr.rolling(72).mean()
    df["expansion_ratio"] = df["atr14"] / df["atr_base"]

    info = mt5.symbol_info(sym)
    point = info.point
    spread_pad = 20 * point if "JPY" not in sym and sym != "XAUUSD" and sym != "BTCUSD" else (60 * point if sym == "XAUUSD" else (300 * point if sym == "BTCUSD" else 15 * point))

    trades_legacy = []
    trades_updated = []

    i = 80
    n = len(df) - 300
    while i < n:
        row = df.iloc[i]
        if row["expansion_ratio"] >= 1.15 and not pd.isna(row["atr14"]) and row["atr14"] > 0:
            atr = row["atr14"]
            entry_price = row["close"]
            sl_dist = atr * 0.8
            tp_dist = atr * 2.5
            
            fwd = df.iloc[i+1 : i + 865]
            if len(fwd) < 15:
                i += 1
                continue

            # --- LEGACY VISION (Old: Static 2.5R TP, Late 1.0R BE, 0.01L, No TTL) ---
            leg_exit_r = 0.0
            leg_dur_bars = 0
            leg_be = False
            leg_sl = entry_price - sl_dist

            for b_idx, (_, b) in enumerate(fwd.iterrows()):
                hi, lo = b["high"], b["low"]
                if not leg_be and hi >= (entry_price + sl_dist):
                    leg_be = True
                    leg_sl = entry_price
                if lo <= leg_sl:
                    leg_exit_r = 0.0 if leg_be else -1.0
                    leg_dur_bars = b_idx + 1
                    break
                if hi >= (entry_price + tp_dist):
                    leg_exit_r = 2.50
                    leg_dur_bars = b_idx + 1
                    break
            else:
                leg_exit_r = (fwd.iloc[-1]["close"] - entry_price) / sl_dist
                leg_dur_bars = len(fwd)
            trades_legacy.append((leg_exit_r, leg_dur_bars))

            # --- UPDATED VISION (Fast Profit Protection: +0.75R BE, +1.2R Trail, +1.40R 50% Harvest, 60m TTL) ---
            upd_exit_r = 0.0
            upd_dur_bars = 0
            upd_be = False
            upd_harvested = False
            upd_sl = entry_price - sl_dist

            for b_idx, (_, b) in enumerate(fwd.iterrows()):
                hi, lo = b["high"], b["low"]

                # 1. Tier 1 Fast BE Lock (+0.75R)
                if not upd_be and hi >= (entry_price + 0.75 * sl_dist):
                    upd_be = True
                    upd_sl = entry_price + spread_pad

                # 2. Tier 3 Dynamic M5 2-Candle Extreme Trailing (Activates >= +1.20R)
                if hi >= (entry_price + 1.20 * sl_dist) and b_idx >= 2:
                    p1 = fwd.iloc[b_idx - 1]["low"]
                    p2 = fwd.iloc[b_idx - 2]["low"]
                    candle_sl = min(p1, p2) - spread_pad
                    if candle_sl > upd_sl:
                        upd_sl = candle_sl

                # 3. Tier 2 Rapid 50% Harvest (+1.40R)
                if not upd_harvested and hi >= (entry_price + 1.40 * sl_dist):
                    upd_harvested = True

                # Check Stop / Trail Exit
                if lo <= upd_sl:
                    base_loss = (upd_sl - entry_price) / sl_dist
                    if upd_harvested:
                        upd_exit_r = (1.40 * 0.5) + (base_loss * 0.5)
                    else:
                        upd_exit_r = base_loss if upd_be else -1.0
                    upd_dur_bars = b_idx + 1
                    break

                # Check Full Hard TP (2.50R)
                if hi >= (entry_price + tp_dist):
                    if upd_harvested:
                        upd_exit_r = (1.40 * 0.5) + (2.50 * 0.5)
                    else:
                        upd_exit_r = 2.50
                    upd_dur_bars = b_idx + 1
                    break
            else:
                upd_exit_r = (fwd.iloc[-1]["close"] - entry_price) / sl_dist
                upd_dur_bars = len(fwd)
            trades_updated.append((upd_exit_r, upd_dur_bars))

            i += max(12, min(leg_dur_bars, upd_dur_bars))
        else:
            i += 1

    leg_r = [t[0] for t in trades_legacy]
    leg_dur = [t[1] * 5 / 60 for t in trades_legacy]
    upd_r = [t[0] for t in trades_updated]
    upd_dur = [t[1] * 5 / 60 for t in trades_updated]

    results.append({
        "Symbol": sym,
        "Total Trades": len(leg_r),
        "Legacy Net R": sum(leg_r),
        "Legacy WinRate": f"{(sum(1 for r in leg_r if r > 0) / len(leg_r) * 100):.1f}%" if leg_r else "0%",
        "Legacy Avg Hold": f"{np.mean(leg_dur):.1f}h" if leg_dur else "0h",
        "Updated Net R": sum(upd_r),
        "Updated WinRate": f"{(sum(1 for r in upd_r if r > 0) / len(upd_r) * 100):.1f}%" if upd_r else "0%",
        "Updated Avg Hold": f"{np.mean(upd_dur):.1f}h" if upd_dur else "0h",
        "Hold Cut": f"{((np.mean(leg_dur) - np.mean(upd_dur)) / np.mean(leg_dur) * 100):.1f}%" if leg_dur and np.mean(leg_dur) > 0 else "0%"
    })

mt5.shutdown()

print("\n" + "=" * 115)
print("ANNUAL COMPARISON MATRIX: LEGACY ARCHITECTURE vs UPDATED FAST PROFIT PROTECTION")
print("=" * 115)
print(f"{'Symbol':<8} | {'Trades':<6} | {'Legacy Net R':<13} | {'Legacy WR':<10} | {'Legacy Hold':<12} | {'Updated Net R':<14} | {'Updated WR':<11} | {'Updated Hold':<13} | {'Hold Cut'}")
print("-" * 115)
for r in results:
    print(f"{r['Symbol']:<8} | {r['Total Trades']:<6} | {r['Legacy Net R']:<13.2f} | {r['Legacy WinRate']:<10} | {r['Legacy Avg Hold']:<12} | {r['Updated Net R']:<14.2f} | {r['Updated WinRate']:<11} | {r['Updated Avg Hold']:<13} | {r['Hold Cut']}")
print("=" * 115)