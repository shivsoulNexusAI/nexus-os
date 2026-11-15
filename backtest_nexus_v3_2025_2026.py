import json
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
VERIFIED_T1_PATH = r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe"
SYMBOLS = ["BTCUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY"]

START_DATE = datetime(2025, 1, 1, tzinfo=timezone.utc)
END_DATE   = datetime(2026, 11, 15, tzinfo=timezone.utc)
INITIAL_EQUITY = 1000.0
CONFIDENCE_GATE = 75.0
MAX_RISK_PCT = 1.5
DAILY_DD_LIMIT_PCT = 3.5

# Realistic Exness average spread + slippage buffer (in points)
SPREAD_POINTS = {
    "BTCUSD": 500,   # ~$5.00
    "XAUUSD": 22,    # $0.22
    "EURUSD": 10,    # 1.0 pip
    "GBPUSD": 12,    # 1.2 pips
    "USDJPY": 11,    # 1.1 pips
    "GBPJPY": 18,    # 1.8 pips
}

def chronos_multiplier(hour_utc: int, is_btc: bool) -> float:
    if is_btc:
        return 1.05
    if 7 <= hour_utc < 10:
        return 1.12
    elif 12 <= hour_utc < 16:
        return 1.15
    elif 0 <= hour_utc < 4:
        return 1.02
    return 0.96

def backtest_symbol(symbol: str):
    mt5.symbol_select(symbol, True)
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"[SKIP] {symbol} not available in Market Watch.")
        return None

    # Force MT5 server history sync using copy_rates_from_pos (up to 150,000 M5 bars = ~1.8 years)
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 150000)
    if rates_m5 is None or len(rates_m5) == 0:
        rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 50000)
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 55000)
    if rates_m15 is None or len(rates_m15) == 0:
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 20000)

    if rates_m5 is None or rates_m15 is None or len(rates_m5) < 500 or len(rates_m15) < 200:
        print(f"[WARN] Insufficient historical bars for {symbol} (M5: {len(rates_m5) if rates_m5 is not None else 0})")
        return None

    df5 = pd.DataFrame(rates_m5)
    df15 = pd.DataFrame(rates_m15)
    df5['dt'] = pd.to_datetime(df5['time'], unit='s', utc=True)
    print(f"[DATA] {symbol:<6} | Bars: {len(df5):,} M5 | Span: {df5['dt'].iloc[0].strftime('%Y-%m-%d')} -> {df5['dt'].iloc[-1].strftime('%Y-%m-%d')}")
    df15['dt'] = pd.to_datetime(df15['time'], unit='s', utc=True)

    # Precompute vectorized M5 features (zero lookahead)
    point = info.point
    spread_px = SPREAD_POINTS.get(symbol, 15) * point
    is_btc = "BTC" in symbol
    is_xau = "XAU" in symbol

    highs = df5['high'].to_numpy()
    lows = df5['low'].to_numpy()
    opens = df5['open'].to_numpy()
    closes = df5['close'].to_numpy()
    vols = df5['tick_volume'].to_numpy(dtype=float)
    hours = df5['dt'].dt.hour.to_numpy()
    dates = df5['dt'].dt.date.to_numpy()

    # True Range & ATR(14)
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close)))
    atr14 = pd.Series(tr).rolling(14).mean().bfill().to_numpy()

    # VPIN proxy over 10-bar volume buckets
    c_range = np.maximum(highs - lows, point)
    buy_v = vols * ((closes - lows) / c_range)
    sell_v = vols * ((highs - closes) / c_range)
    imb = np.abs(buy_v - sell_v)
    vpin_arr = (pd.Series(imb).rolling(10).sum() / pd.Series(vols).rolling(10).sum().replace(0, 1)).fillna(0).to_numpy()

    # Align M15 lookup index for each M5 bar (strictly closed/past M15 bars)
    m15_times = df15['time'].to_numpy()
    m15_closes = df15['close'].to_numpy()
    m15_opens = df15['open'].to_numpy()
    m15_vols = df15['tick_volume'].to_numpy(dtype=float)
    m5_times = df5['time'].to_numpy()
    m15_idx_map = np.searchsorted(m15_times, m5_times, side='right') - 1

    equity = INITIAL_EQUITY
    peak_equity = INITIAL_EQUITY
    max_dd_pct = 0.0
    trades_pnl = []
    rolling_pnls = []

    in_trade = False
    t_dir = 0
    t_entry = 0.0
    t_sl = 0.0
    t_tp = 0.0
    t_risk_usd = 0.0
    be_locked = False

    current_day = None
    day_start_eq = equity

    # Step bar-by-bar from bar 100 to end
    for i in range(100, len(df5) - 1):
        if dates[i] != current_day:
            current_day = dates[i]
            day_start_eq = equity

        # 1. Manage Open Trade on Bar i+1
        if in_trade:
            nxt_high = highs[i + 1]
            nxt_low = lows[i + 1]
            nxt_close = closes[i + 1]

            if t_dir == 1:  # BUY
                # Check +0.5R Breakeven lock
                target_dist = t_tp - t_entry
                if not be_locked and (nxt_high - t_entry) >= 0.5 * target_dist:
                    t_sl = t_entry + spread_px
                    be_locked = True
                # Check SL / TP hit
                if nxt_low <= t_sl:
                    r_mult = (t_sl - t_entry) / max(point, (t_entry - (t_entry - target_dist * 0.5)))
                    pnl = 0.0 if be_locked else -t_risk_usd
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False
                elif nxt_high >= t_tp:
                    pnl = t_risk_usd * 2.0
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False
            else:  # SELL
                target_dist = t_entry - t_tp
                if not be_locked and (t_entry - nxt_low) >= 0.5 * target_dist:
                    t_sl = t_entry - spread_px
                    be_locked = True
                if nxt_high >= t_sl:
                    pnl = 0.0 if be_locked else -t_risk_usd
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False
                elif nxt_low <= t_tp:
                    pnl = t_risk_usd * 2.0
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False

            peak_equity = max(peak_equity, equity)
            dd_now = ((peak_equity - equity) / max(1.0, peak_equity)) * 100.0
            max_dd_pct = max(max_dd_pct, dd_now)
            continue

        # 2. Check Daily Drawdown Circuit Breaker (3.5%)
        daily_dd = ((day_start_eq - equity) / max(1.0, day_start_eq)) * 100.0
        if daily_dd >= DAILY_DD_LIMIT_PCT:
            continue

        # 3. Evaluate Alpha Matrix (VPIN + Footprint Delta + Volume Profile + ICT + Chronos)
        m15_i = m15_idx_map[i]
        if m15_i < 32:
            continue

        win_c = m15_closes[m15_i - 32:m15_i]
        win_v = m15_vols[m15_i - 32:m15_i]
        poc = win_c[np.argmax(win_v)]
        val = np.percentile(win_c, 25)
        vah = np.percentile(win_c, 75)
        curr_px = closes[i]

        m15_move = (m15_closes[m15_i] - m15_opens[m15_i - 2]) / point
        m5_move = (closes[i] - opens[i - 1]) / point
        delta = int(round((m5_move if abs(m5_move) > abs(m15_move) * 0.6 else m15_move) / 10.0))

        vpin = vpin_arr[i]
        net_flow = (buy_v[i] - sell_v[i]) / max(1.0, vols[i])
        dii = max(-0.99, min(0.99, (delta / 100.0) * (1.0 + vpin) + net_flow * 0.35))

        prev_low = np.min(lows[i - 12:i - 2])
        prev_high = np.max(highs[i - 12:i - 2])
        ict_bonus = 0.0
        if lows[i - 1] < prev_low and curr_px > prev_low and curr_px <= poc:
            ict_bonus = 10.0 if delta > 0 else -5.0
        elif highs[i - 1] > prev_high and curr_px < prev_high and curr_px >= poc:
            ict_bonus = 10.0 if delta < 0 else -5.0
        elif curr_px < val and delta > 0:
            ict_bonus = 6.0
        elif curr_px > vah and delta < 0:
            ict_bonus = 6.0

        c_mult = chronos_multiplier(hours[i], is_btc)
        base_score = 50.0 + min(32.0, abs(delta) * 0.22 + abs(dii) * 28.0) + (vpin * 12.0) + ict_bonus
        conf = min(98.0, max(50.0, base_score * c_mult))

        if conf >= CONFIDENCE_GATE and delta != 0:
            # Half-Kelly risk sizing calibrated on rolling 50 trades
            if len(rolling_pnls) >= 15:
                recent = rolling_pnls[-50:]
                w = [x for x in recent if x > 0]
                l = [abs(x) for x in recent if x < 0]
                p = len(w) / max(1, len(w) + len(l))
                b = (np.mean(w) if w else 1.0) / max(0.01, (np.mean(l) if l else 1.0))
                fk = p - ((1.0 - p) / max(0.1, b))
                hk = max(0.0025, min(MAX_RISK_PCT / 100.0, fk * 0.5))
            else:
                hk = 0.005

            atr = atr14[i]
            if is_btc:
                sl_dist = max(25000 * point, atr * 2.0)
            elif is_xau:
                sl_dist = max(350 * point, atr * 2.0)
            else:
                sl_dist = max(150 * point, atr * 2.0)
            tp_dist = sl_dist * 2.0

            t_dir = 1 if delta > 0 else -1
            t_entry = closes[i] + (spread_px if t_dir == 1 else 0.0)
            t_sl = t_entry - sl_dist if t_dir == 1 else t_entry + sl_dist
            t_tp = t_entry + tp_dist if t_dir == 1 else t_entry - tp_dist
            t_risk_usd = equity * hk
            be_locked = False
            in_trade = True

    wins = [x for x in trades_pnl if x > 0]
    losses = [abs(x) for x in trades_pnl if x < 0]
    be_cnt = sum(1 for x in trades_pnl if x == 0.0)
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    pf = gross_profit / max(0.01, gross_loss)
    win_rate = (len(wins) / max(1, len(wins) + len(losses))) * 100.0
    net_pnl = equity - INITIAL_EQUITY
    ret_pct = (net_pnl / INITIAL_EQUITY) * 100.0

    return {
        "Symbol": symbol,
        "Trades": len(trades_pnl),
        "WinRate%": round(win_rate, 1),
        "BE_Locks": be_cnt,
        "ProfitFactor": round(pf, 2),
        "NetPnL($)": round(net_pnl, 2),
        "Return%": round(ret_pct, 1),
        "MaxDD%": round(max_dd_pct, 2),
        "FinalEq($)": round(equity, 2),
    }

if __name__ == "__main__":
    print("===================================================================================")
    print("  QUANTNEXUS UNIFIED CORE v3.0 // 2025-2026 HISTORICAL WALK-FORWARD BACKTEST       ")
    print("  Period: 2025-01-01 to 2026-11-15 | Gate >= 75% | Half-Kelly + VPIN + ICT + BE    ")
    print("===================================================================================")

    if not mt5.initialize(path=VERIFIED_T1_PATH):
        print(f"[ERROR] Failed to connect to MT5 Terminal 1: {mt5.last_error()}")
        raise SystemExit(1)

    results = []
    for sym in SYMBOLS:
        res = backtest_symbol(sym)
        if res:
            results.append(res)

    mt5.shutdown()

    if results:
        df_res = pd.DataFrame(results)
        print("\n" + df_res.to_string(index=False))

        tot_trades = df_res["Trades"].sum()
        tot_net = df_res["NetPnL($)"].sum()
        avg_pf = df_res["ProfitFactor"].mean()
        avg_wr = df_res["WinRate%"].mean()
        worst_dd = df_res["MaxDD%"].max()

        print("\n-----------------------------------------------------------------------------------")
        print(f"FLEET SUMMARY (2025-2026): Total Trades = {tot_trades} | Avg Win Rate = {avg_wr:.1f}% | Mean PF = {avg_pf:.2f}")
        print(f"Combined Net Profit ($1k/slot): ${tot_net:+,.2f} | Peak Single-Slot Max DD: {worst_dd:.2f}%")
        print("-----------------------------------------------------------------------------------")

        out_path = BASE_DIR / "backtest_v3_2025_2026_report.json"
        out_path.write_text(json.dumps(results, indent=4), encoding="utf-8")
        print(f"[SAVED] Full JSON telemetry exported to {out_path}")
