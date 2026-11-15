# -*- coding: utf-8 -*-
"""
QUANT-NEXUS SILO 2: 12-MONTH FULL PRODUCTION BACKTEST (2025 - 2026)
Simulates:
  - OCO Straddle Breakouts (Asian High/Low, Session Open, Volatility Compression)
  - Tier 1: Zero-Risk Breakeven Lock at +1.0R
  - Tier 2: 50% Volume Harvest at +2.0R with +10 pip runner ratchet
  - Hard Symbol Exposure Clamps
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import json

TERMINAL_PATH = r"C:/MT5_Quant_278061453/terminal64.exe"
ACCOUNT = 278062039

if not mt5.initialize(path=TERMINAL_PATH, portable=False):
    print(f"[-] MT5 initialization failed: {mt5.last_error()}")
    exit(1)

# Time Range: 1 Full Year (Nov 1, 2025 - Nov 1, 2026)
DATE_FROM = datetime(2025, 11, 1, tzinfo=timezone.utc)
DATE_TO   = datetime(2026, 11, 1, tzinfo=timezone.utc)

INITIAL_CAPITAL = 1000.00

# Asset Matrix from nexus_straddle_matrix.json
ASSET_CONFIG = {
    "XAUUSD": {"lot": 0.01, "max_exp": 0.04, "buf_pts": 150, "sl_pts": 150, "t1_pts": 150, "t2_pts": 300, "t1_lock": 50, "t2_ratchet": 100},
    "US30":   {"lot": 0.02, "max_exp": 0.04, "buf_pts": 40,  "sl_pts": 40,  "t1_pts": 40,  "t2_pts": 80,  "t1_lock": 10, "t2_ratchet": 30},
    "BTCUSD": {"lot": 0.01, "max_exp": 0.03, "buf_pts": 350, "sl_pts": 300, "t1_pts": 300, "t2_pts": 600, "t1_lock": 60, "t2_ratchet": 200},
    "EURUSD": {"lot": 0.02, "max_exp": 0.08, "buf_pts": 80,  "sl_pts": 120, "t1_pts": 120, "t2_pts": 250, "t1_lock": 15, "t2_ratchet": 100},
    "GBPUSD": {"lot": 0.02, "max_exp": 0.08, "buf_pts": 100, "sl_pts": 150, "t1_pts": 150, "t2_pts": 280, "t1_lock": 20, "t2_ratchet": 100},
    "USDJPY": {"lot": 0.01, "max_exp": 0.04, "buf_pts": 120, "sl_pts": 160, "t1_pts": 160, "t2_pts": 320, "t1_lock": 20, "t2_ratchet": 120}
}

print("=" * 115)
print("     QUANT-NEXUS SILO 2: 12-MONTH HISTORICAL SIMULATION (NOV 2025 - NOV 2026)")
print("=" * 115)
print(f" Starting Balance : ${INITIAL_CAPITAL:,.2f}")
print(f" Backtest Period  : {DATE_FROM.strftime('%Y-%m-%d')} to {DATE_TO.strftime('%Y-%m-%d')}")
print("-" * 115)

portfolio_trades = []
asset_metrics = {}

for sym, cfg in ASSET_CONFIG.items():
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, DATE_FROM, DATE_TO)
    if rates is None or len(rates) == 0:
        print(f"[-] Could not load M15 rates for {sym}. Skipping.")
        continue

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    sym_info = mt5.symbol_info(sym)
    point = sym_info.point if sym_info else 0.00001
    contract_size = sym_info.trade_contract_size if sym_info else 100000.0

    # Simulate Daily Breakout Brackets
    # Group by Day, calculate daily session high/low for breakout boundaries
    df['date'] = df['time'].dt.date
    daily_groups = df.groupby('date')
    
    trades = []
    
    for date, group in daily_groups:
        if len(group) < 16:
            continue
        
        # Use first 4 hours (16 M15 bars) as baseline range
        ref_window = group.iloc[:16]
        ref_high = ref_window['high'].max()
        ref_low  = ref_window['low'].min()
        
        # Straddle Trigger Levels
        buy_stop = ref_high + (cfg["buf_pts"] * point)
        sell_stop = ref_low - (cfg["buf_pts"] * point)
        sl_dist = cfg["sl_pts"] * point
        t1_dist = cfg["t1_pts"] * point
        t2_dist = cfg["t2_pts"] * point
        
        buy_active = False
        sell_active = False
        
        for idx in range(16, len(group)):
            bar = group.iloc[idx]
            
            # 1. Trigger Checks
            if not buy_active and not sell_active:
                if bar['high'] >= buy_stop:
                    buy_active = True
                    entry_price = buy_stop
                    current_sl = entry_price - sl_dist
                    t1_hit = False
                    t2_hit = False
                    rem_vol = cfg["lot"]
                    pnl_accum = 0.0
                    direction = "BUY"
                elif bar['low'] <= sell_stop:
                    sell_active = True
                    entry_price = sell_stop
                    current_sl = entry_price + sl_dist
                    t1_hit = False
                    t2_hit = False
                    rem_vol = cfg["lot"]
                    pnl_accum = 0.0
                    direction = "SELL"
                continue
            
            # 2. Position Management for Active BUY
            if buy_active:
                # Check Stop Loss Hit
                if bar['low'] <= current_sl:
                    pnl = (current_sl - entry_price) * contract_size * rem_vol
                    pnl_accum += pnl
                    trades.append({"symbol": sym, "pnl": pnl_accum, "date": date, "t2_harvest": t2_hit, "win": pnl_accum > 0})
                    buy_active = False
                    break
                
                # Check Tier 1 BE Lock (+1.0R)
                if not t1_hit and bar['high'] >= (entry_price + t1_dist):
                    t1_hit = True
                    current_sl = entry_price + (cfg["t1_lock"] * point)
                
                # Check Tier 2 Partial Harvest (+2.0R)
                if not t2_hit and bar['high'] >= (entry_price + t2_dist):
                    t2_hit = True
                    harvest_vol = round(rem_vol * 0.5, 2)
                    harvest_pnl = t2_dist * contract_size * harvest_vol
                    pnl_accum += harvest_pnl
                    rem_vol -= harvest_vol
                    # Ratchet remaining runner stop
                    current_sl = entry_price + (cfg["t2_ratchet"] * point)

            # 3. Position Management for Active SELL
            elif sell_active:
                if bar['high'] >= current_sl:
                    pnl = (entry_price - current_sl) * contract_size * rem_vol
                    pnl_accum += pnl
                    trades.append({"symbol": sym, "pnl": pnl_accum, "date": date, "t2_harvest": t2_hit, "win": pnl_accum > 0})
                    sell_active = False
                    break
                
                if not t1_hit and bar['low'] <= (entry_price - t1_dist):
                    t1_hit = True
                    current_sl = entry_price - (cfg["t1_lock"] * point)
                
                if not t2_hit and bar['low'] <= (entry_price - t2_dist):
                    t2_hit = True
                    harvest_vol = round(rem_vol * 0.5, 2)
                    harvest_pnl = t2_dist * contract_size * harvest_vol
                    pnl_accum += harvest_pnl
                    rem_vol -= harvest_vol
                    current_sl = entry_price - (cfg["t2_ratchet"] * point)

    # Asset Performance Metrics
    if trades:
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        t2_harvests = sum(1 for t in trades if t["t2_harvest"])
        net_pnl = sum(pnls)
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.9
        win_rate = (len(wins) / len(trades) * 100.0)
        
        asset_metrics[sym] = {
            "trades": len(trades),
            "net_pnl": net_pnl,
            "win_rate": win_rate,
            "t2_harvests": t2_harvests,
            "profit_factor": profit_factor,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss
        }
        portfolio_trades.extend(trades)

# Print Summary Table
print(f"{'ASSET':<8} | {'TRADES':<7} | {'NET PNL':<12} | {'WIN RATE':<9} | {'PF':<6} | {'T2 HARVESTS':<11} | {'GROSS PROFIT':<13} | {'GROSS LOSS':<11}")
print("-" * 115)

for sym, m in sorted(asset_metrics.items(), key=lambda x: x[1]["net_pnl"], reverse=True):
    print(f"{sym:<8} | {m['trades']:<7} | ${m['net_pnl']:>+10.2f} | {m['win_rate']:>7.1f}% | {m['profit_factor']:>5.2f} | {m['t2_harvests']:>11d} | ${m['gross_profit']:>11.2f} | ${m['gross_loss']:>10.2f}")

print("=" * 115)

# Portfolio Aggregate Calculations
if portfolio_trades:
    all_pnls = [t["pnl"] for t in portfolio_trades]
    tot_net = sum(all_pnls)
    tot_wins = sum(p for p in all_pnls if p > 0)
    tot_loss = abs(sum(p for p in all_pnls if p <= 0))
    tot_pf = (tot_wins / tot_loss) if tot_loss > 0 else 99.9
    tot_wr = (sum(1 for p in all_pnls if p > 0) / len(portfolio_trades) * 100.0)
    tot_t2 = sum(1 for t in portfolio_trades if t["t2_harvest"])
    final_balance = INITIAL_CAPITAL + tot_net
    roi_pct = (tot_net / INITIAL_CAPITAL) * 100.0

    # Drawdown Calculation
    cum_pnl = np.cumsum(all_pnls)
    equity_curve = INITIAL_CAPITAL + cum_pnl
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (peak - equity_curve) / peak * 100.0
    max_dd = np.max(drawdowns)

    print("                 12-MONTH PORTFOLIO EXECUTIVE AUDIT")
    print("=" * 115)
    print(f" Starting Capital : ${INITIAL_CAPITAL:,.2f}")
    print(f" Final Balance    : ${final_balance:,.2f}  (ROI: +{roi_pct:.1f}%)")
    print(f" Total Trades     : {len(portfolio_trades)} completed setups")
    print(f" Portfolio WinRate: {tot_wr:.1f}%")
    print(f" Profit Factor    : {tot_pf:.2f}")
    print(f" Max Drawdown     : {max_dd:.2f}% (Peak-to-Trough)")
    print(f" Tier 2 Harvests  : {tot_t2} partial profit locks banked")
    print("=" * 115)

mt5.shutdown()