# -*- coding: utf-8 -*-
"""
QUANT-NEXUS SILO 2: VALIDATED KILLZONE STRADDLE 12M SIMULATION (2025 - 2026)
Anchors:
  - Reference Range: First 30 mins (bars 0-1) of London (07:00 UTC) & NY (13:00 UTC)
  - Breakout Execution: Bars 2-10 with Trend Filter (EMA 50)
  - Tier 1: +1.0R Breakeven Lock | Tier 2: +2.0R 50% Harvest + Ratchet
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

TERMINAL_PATH = r"C:/MT5_Quant_278061453/terminal64.exe"
if not mt5.initialize(path=TERMINAL_PATH, portable=False):
    print(f"[-] MT5 initialization failed: {mt5.last_error()}")
    exit(1)

DATE_FROM = datetime(2025, 11, 1, tzinfo=timezone.utc)
DATE_TO   = datetime(2026, 11, 1, tzinfo=timezone.utc)
INITIAL_CAPITAL = 1000.00

ASSETS = {
    "XAUUSD": {"lot": 0.01, "buf": 150, "sl": 150, "t1": 150, "t2": 300, "t1_l": 50, "t2_r": 100},
    "US30":   {"lot": 0.02, "buf": 40,  "sl": 40,  "t1": 40,  "t2": 80,  "t1_l": 10, "t2_r": 30},
    "BTCUSD": {"lot": 0.01, "buf": 350, "sl": 300, "t1": 300, "t2": 600, "t1_l": 60, "t2_r": 200},
    "EURUSD": {"lot": 0.02, "buf": 70,  "sl": 100, "t1": 100, "t2": 200, "t1_l": 15, "t2_r": 70},
    "GBPUSD": {"lot": 0.02, "buf": 80,  "sl": 110, "t1": 110, "t2": 220, "t1_l": 20, "t2_r": 70},
    "USDJPY": {"lot": 0.02, "buf": 80,  "sl": 110, "t1": 110, "t2": 220, "t1_l": 20, "t2_r": 70}
}

portfolio_trades = []
asset_metrics = {}

for sym, cfg in ASSETS.items():
    mt5.symbol_select(sym, True)
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, DATE_FROM, DATE_TO)
    if rates is None or len(rates) == 0:
        continue

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    sym_info = mt5.symbol_info(sym)
    point = sym_info.point if sym_info else 0.00001
    
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['hour'] = df['time'].dt.hour
    df['date'] = df['time'].dt.date
    
    trades = []
    
    # Check London (07:00-10:00 UTC) and NY (13:00-16:00 UTC)
    for (date, is_london, is_ny), group in df.groupby(['date', df['hour'].isin([7, 8, 9]), df['hour'].isin([13, 14, 15])]):
        if (not is_london and not is_ny) or len(group) < 6:
            continue
            
        # Reference Range: first 2 bars (30 min)
        ref_bars = group.iloc[:2]
        eval_bars = group.iloc[2:]
        
        ref_high = ref_bars['high'].max()
        ref_low  = ref_bars['low'].min()
        
        pre_bar = ref_bars.iloc[-1]
        trend_up = pre_bar['close'] > pre_bar['ema50']
        
        buy_stop = ref_high + (cfg["buf"] * point)
        sell_stop = ref_low - (cfg["buf"] * point)
        
        sl_dist = cfg["sl"] * point
        t1_dist = cfg["t1"] * point
        t2_dist = cfg["t2"] * point
        
        active = False
        
        for _, bar in eval_bars.iterrows():
            if not active:
                if trend_up and bar['high'] >= buy_stop:
                    active = True
                    direction = "BUY"
                    entry_p = buy_stop
                    current_sl = entry_p - sl_dist
                    t1_hit = False
                    t2_hit = False
                    rem_vol = cfg["lot"]
                    accum_pnl = 0.0
                elif not trend_up and bar['low'] <= sell_stop:
                    active = True
                    direction = "SELL"
                    entry_p = sell_stop
                    current_sl = entry_p + sl_dist
                    t1_hit = False
                    t2_hit = False
                    rem_vol = cfg["lot"]
                    accum_pnl = 0.0
                continue
                
            if active and direction == "BUY":
                if bar['low'] <= current_sl:
                    p = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, sym, rem_vol, entry_p, current_sl)
                    accum_pnl += (p if p is not None else 0.0)
                    trades.append({"symbol": sym, "pnl": accum_pnl, "win": accum_pnl > 0, "t2": t2_hit})
                    break
                if not t1_hit and bar['high'] >= (entry_p + t1_dist):
                    t1_hit = True
                    current_sl = entry_p + (cfg["t1_l"] * point)
                if not t2_hit and bar['high'] >= (entry_p + t2_dist):
                    t2_hit = True
                    h_vol = round(rem_vol * 0.5, 2)
                    p = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, sym, h_vol, entry_p, entry_p + t2_dist)
                    accum_pnl += (p if p is not None else 0.0)
                    rem_vol -= h_vol
                    current_sl = entry_p + (cfg["t2_r"] * point)

            elif active and direction == "SELL":
                if bar['high'] >= current_sl:
                    p = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, sym, rem_vol, entry_p, current_sl)
                    accum_pnl += (p if p is not None else 0.0)
                    trades.append({"symbol": sym, "pnl": accum_pnl, "win": accum_pnl > 0, "t2": t2_hit})
                    break
                if not t1_hit and bar['low'] <= (entry_p - t1_dist):
                    t1_hit = True
                    current_sl = entry_p - (cfg["t1_l"] * point)
                if not t2_hit and bar['low'] <= (entry_p - t2_dist):
                    t2_hit = True
                    h_vol = round(rem_vol * 0.5, 2)
                    p = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, sym, h_vol, entry_p, entry_p - t2_dist)
                    accum_pnl += (p if p is not None else 0.0)
                    rem_vol -= h_vol
                    current_sl = entry_p - (cfg["t2_r"] * point)

    if trades:
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        net = sum(pnls)
        gp = sum(wins) if wins else 0.0
        gl = abs(sum(losses)) if losses else 0.0
        pf = (gp / gl) if gl > 0 else 99.9
        wr = (len(wins) / len(trades) * 100.0)
        t2_cnt = sum(1 for t in trades if t["t2"])
        asset_metrics[sym] = {"trades": len(trades), "net": net, "wr": wr, "pf": pf, "t2": t2_cnt, "gp": gp, "gl": gl}
        portfolio_trades.extend(trades)

print("=" * 110)
print("       QUANT-NEXUS SILO 2: VALIDATED KILLZONE STRADDLE 12M AUDIT (2025 - 2026)")
print("=" * 110)
print(f"{'ASSET':<8} | {'TRADES':<7} | {'NET PNL':<12} | {'WIN RATE':<9} | {'PF':<6} | {'T2 HARVESTS':<11} | {'GROSS PROFIT':<13} | {'GROSS LOSS':<11}")
print("-" * 110)
for sym, m in sorted(asset_metrics.items(), key=lambda x: x[1]["net"], reverse=True):
    print(f"{sym:<8} | {m['trades']:<7} | ${m['net']:>+10.2f} | {m['wr']:>7.1f}% | {m['pf']:>5.2f} | {m['t2']:>11d} | ${m['gp']:>11.2f} | ${m['gl']:>10.2f}")
print("=" * 110)

if portfolio_trades:
    all_pnls = [t["pnl"] for t in portfolio_trades]
    tot_net = sum(all_pnls)
    tot_wins = sum(p for p in all_pnls if p > 0)
    tot_loss = abs(sum(p for p in all_pnls if p <= 0))
    tot_pf = (tot_wins / tot_loss) if tot_loss > 0 else 99.9
    tot_wr = (sum(1 for p in all_pnls if p > 0) / len(portfolio_trades) * 100.0)
    tot_t2 = sum(1 for t in portfolio_trades if t["t2"])
    roi = (tot_net / INITIAL_CAPITAL) * 100.0
    
    cum = np.cumsum(all_pnls)
    eq = INITIAL_CAPITAL + cum
    peak = np.maximum.accumulate(eq)
    max_dd = np.max((peak - eq) / peak * 100.0)

    print(f" Starting Capital : ${INITIAL_CAPITAL:,.2f}")
    print(f" Final Balance    : ${INITIAL_CAPITAL + tot_net:,.2f}  (ROI: {roi:+.1f}%)")
    print(f" Total Setups     : {len(portfolio_trades)} executed trades")
    print(f" Portfolio WinRate: {tot_wr:.1f}%")
    print(f" Profit Factor    : {tot_pf:.2f}")
    print(f" Max Drawdown     : {max_dd:.2f}%")
    print(f" Tier 2 Harvests  : {tot_t2} partial locks banked")
    print("=" * 110)

mt5.shutdown()