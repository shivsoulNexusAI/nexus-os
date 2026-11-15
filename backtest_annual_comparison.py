import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
START_DATE = datetime(2025, 11, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 11, 1, tzinfo=timezone.utc)

if not mt5.initialize(path=TERMINAL, portable=False):
    print("[-] MT5 Init failed.")
    exit(1)

print("=" * 95)
print(f"1-YEAR HISTORICAL BACKTEST (2025-11-01 to 2026-11-01) ACROSS 5 ASSETS")
print("Evaluating Legacy Vision vs Updated Fast Profit Protection Suite")
print("=" * 95)

results = []

for sym in SYMBOLS:
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, START_DATE, END_DATE)
    if rates is None or len(rates) < 500:
        print(f"[-] Insufficient historical M5 data for {sym}")
        continue
        
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    
    # Calculate indicators
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
    df["atr14"] = tr.rolling(14).mean()
    df["atr_base"] = tr.rolling(72).mean()
    df["expansion_ratio"] = df["atr14"] / df["atr_base"]
    
    info = mt5.symbol_info(sym)
    point = info.point
    spread_pad = 20 * point if "JPY" not in sym and sym != "XAUUSD" and sym != "BTCUSD" else (60 * point if sym == "XAUUSD" else (300 * point if sym == "BTCUSD" else 15 * point))

    # Replay simulated straddle entries on expansion signals (> 1.15 ATR ratio)
    trades_legacy = []
    trades_updated = []
    
    i = 80
    n = len(df) - 300
    while i < n:
        row = df.iloc[i]
        if row["expansion_ratio"] >= 1.15 and not pd.isna(row["atr14"]):
            atr = row["atr14"]
            entry_price = row["close"]
            sl_dist = atr * 0.8
            tp_dist = atr * 2.5
            
            # Simulate a BUY breakout leg
            # Track forward bars
            # 1. LEGACY VISION: Fixed TP (2.5R), Fixed SL, BE at +1.0R (requires full run)
            # 2. UPDATED VISION: +0.75R BE Lock, +1.2R M5 Trail, +1.40R 50% Harvest, 60m TTL
            
            # Look ahead up to 72 hours (864 bars)
            fwd = df.iloc[i+1 : i + 865]
            
            # --- LEGACY REPLAY ---
            leg_exit_r = 0.0
            leg_duration_bars = 0
            leg_be_locked = False
            leg_sl = entry_price - sl_dist
            
            for bar_idx, (_, b) in enumerate(fwd.iterrows()):
                high, low = b["high"], b["low"]
                # Check BE move (+1.0R)
                if not leg_be_locked and high >= (entry_price + sl_dist):
                    leg_be_locked = True
                    leg_sl = entry_price
                # Check SL
                if low <= leg_sl:
                    leg_exit_r = 0.0 if leg_be_locked else -1.0
                    leg_duration_bars = bar_idx + 1
                    break
                # Check TP
                if high >= (entry_price + tp_dist):
                    leg_exit_r = 2.5
                    leg_duration_bars = bar_idx + 1
                    break
            else:
                leg_exit_r = (fwd.iloc[-1]["close"] - entry_price) / sl_dist
                leg_duration_bars = len(fwd)
            trades_legacy.append((leg_exit_r, leg_duration_bars))
            
            # --- UPDATED VISION REPLAY ---
            upd_exit_r = 0.0
            upd_duration_bars = 0
            upd_be_locked = False
            upd_harvested = False
            upd_sl = entry_price - sl_dist
            
            for bar_idx, (_, b) in enumerate(fwd.iterrows()):
                high, low = b["high"], b["low"]
                
                # Check 60-minute order TTL (first 12 bars)
                # Tier 1: Fast BE Lock (+0.75R)
                if not upd_be_locked and high >= (entry_price + 0.75 * sl_dist):
                    upd_be_locked = True
                    upd_sl = entry_price + spread_pad
                    
                # Tier 3: Dynamic Trail (lowest low of last 2 closed bars once >= +1.2R)
                if high >= (entry_price + 1.20 * sl_dist) and bar_idx >= 2:
                    p1 = fwd.iloc[bar_idx - 1]["low"]
                    p2 = fwd.iloc[bar_idx - 2]["low"]
                    candle_sl = min(p1, p2) - spread_pad
                    if candle_sl > upd_sl:
                        upd_sl = candle_sl
                        
                # Tier 2: Rapid 50% Harvest at +1.40R
                if not upd_harvested and high >= (entry_price + 1.40 * sl_dist):
                    upd_harvested = True
                    
                # Check SL / Trail Hit
                if low <= upd_sl:
                    base_loss = (upd_sl - entry_price) / sl_dist
                    if upd_harvested:
                        upd_exit_r = (1.40 * 0.5) + (base_loss * 0.5)
                    else:
                        upd_exit_r = base_loss if upd_be_locked else -1.0
                    upd_duration_bars = bar_idx + 1
                    break
                    
                # Check Hard TP (2.50R)
                if high >= (entry_price + tp_dist):
                    if upd_harvested:
                        upd_exit_r = (1.40 * 0.5) + (2.50 * 0.5)
                    else:
                        upd_exit_r = 2.50
                    upd_duration_bars = bar_idx + 1
                    break
            else:
                upd_exit_r = (fwd.iloc[-1]["close"] - entry_price) / sl_dist
                upd_duration_bars = len(fwd)
            trades_updated.append((upd_exit_r, upd_duration_bars))
            
            i += max(12, min(leg_duration_bars, upd_duration_bars))
        else:
            i += 1
            
    # Aggregate Stats
    leg_r = [t[0] for t in trades_legacy]
    leg_dur = [t[1] * 5 / 60 for t in trades_legacy] # in hours
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
        "Hold Time Cut": f"{((np.mean(leg_dur) - np.mean(upd_dur)) / np.mean(leg_dur) * 100):.1f}%" if leg_dur and np.mean(leg_dur) > 0 else "0%"
    })

mt5.shutdown()

print(f"\n{'Symbol':<8} | {'Trades':<6} | {'Legacy Net R':<12} | {'Legacy WR':<9} | {'Legacy Hold':<11} | {'Updated Net R':<13} | {'Updated WR':<10} | {'Updated Hold':<12} | {'Hold Cut'}")
print("-" * 115)
for r in results:
    print(f"{r['Symbol']:<8} | {r['Total Trades']:<6} | {r['Legacy Net R']:<12.2f} | {r['Legacy WinRate']:<9} | {r['Legacy Avg Hold']:<11} | {r['Updated Net R']:<13.2f} | {r['Updated WinRate']:<10} | {r['Updated Avg Hold']:<12} | {r['Hold Time Cut']}")
print("=" * 115)