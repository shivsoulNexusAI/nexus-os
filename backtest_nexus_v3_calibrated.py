import json
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
VERIFIED_T1_PATH = r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe"
SYMBOLS = ["BTCUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY"]

INITIAL_EQUITY = 1000.0
CONFIDENCE_GATE = 82.0
MAX_RISK_PCT = 0.75
DAILY_DD_LIMIT_PCT = 2.5

SPREAD_POINTS = {
    "BTCUSD": 500,
    "XAUUSD": 22,
    "EURUSD": 10,
    "GBPUSD": 12,
    "USDJPY": 11,
    "GBPJPY": 18,
}

def in_active_killzone(hour_utc: int, is_btc: bool) -> bool:
    if is_btc:
        return 8 <= hour_utc <= 21
    return (7 <= hour_utc <= 10) or (12 <= hour_utc <= 16)

def backtest_calibrated(symbol: str):
    mt5.symbol_select(symbol, True)
    info = mt5.symbol_info(symbol)
    if not info:
        return None

    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 50000)
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 20000)
    if rates_m5 is None or rates_m15 is None or len(rates_m5) < 500:
        return None

    df5 = pd.DataFrame(rates_m5)
    df15 = pd.DataFrame(rates_m15)
    df5['dt'] = pd.to_datetime(df5['time'], unit='s', utc=True)

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

    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close)))
    atr14 = pd.Series(tr).rolling(14).mean().bfill().to_numpy()

    c_range = np.maximum(highs - lows, point)
    buy_v = vols * ((closes - lows) / c_range)
    sell_v = vols * ((highs - closes) / c_range)
    imb = np.abs(buy_v - sell_v)
    vpin_arr = (pd.Series(imb).rolling(10).sum() / pd.Series(vols).rolling(10).sum().replace(0, 1)).fillna(0).to_numpy()

    df15['ema21'] = df15['close'].ewm(span=21, adjust=False).mean()
    df15['ema55'] = df15['close'].ewm(span=55, adjust=False).mean()
    m15_times = df15['time'].to_numpy()
    m15_closes = df15['close'].to_numpy()
    m15_opens = df15['open'].to_numpy()
    m15_vols = df15['tick_volume'].to_numpy(dtype=float)
    m15_ema21 = df15['ema21'].to_numpy()
    m15_ema55 = df15['ema55'].to_numpy()
    m15_idx_map = np.searchsorted(m15_times, df5['time'].to_numpy(), side='right') - 1

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
    t_sl_dist = 0.0
    t_risk_usd = 0.0
    be_locked = False
    cooldown_until = 0

    current_day = None
    day_start_eq = equity

    for i in range(100, len(df5) - 1):
        if dates[i] != current_day:
            current_day = dates[i]
            day_start_eq = equity

        if in_trade:
            nxt_high = highs[i + 1]
            nxt_low = lows[i + 1]

            if t_dir == 1:
                if not be_locked and (nxt_high - t_entry) >= t_sl_dist:
                    t_sl = t_entry + spread_px
                    be_locked = True
                if nxt_low <= t_sl:
                    pnl = 0.0 if be_locked else -t_risk_usd
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False
                    cooldown_until = i + 6
                elif nxt_high >= t_tp:
                    pnl = t_risk_usd * 2.5
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False
                    cooldown_until = i + 6
            else:
                if not be_locked and (t_entry - nxt_low) >= t_sl_dist:
                    t_sl = t_entry - spread_px
                    be_locked = True
                if nxt_high >= t_sl:
                    pnl = 0.0 if be_locked else -t_risk_usd
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False
                    cooldown_until = i + 6
                elif nxt_low <= t_tp:
                    pnl = t_risk_usd * 2.5
                    equity += pnl
                    trades_pnl.append(pnl)
                    rolling_pnls.append(pnl)
                    in_trade = False
                    cooldown_until = i + 6

            peak_equity = max(peak_equity, equity)
            max_dd_pct = max(max_dd_pct, ((peak_equity - equity) / max(1.0, peak_equity)) * 100.0)
            continue

        if i < cooldown_until or not in_active_killzone(hours[i], is_btc):
            continue

        daily_dd = ((day_start_eq - equity) / max(1.0, day_start_eq)) * 100.0
        if daily_dd >= DAILY_DD_LIMIT_PCT:
            continue

        m15_i = m15_idx_map[i]
        if m15_i < 60:
            continue

        bull_regime = m15_ema21[m15_i] > m15_ema55[m15_i]
        bear_regime = m15_ema21[m15_i] < m15_ema55[m15_i]

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

        if vpin < 0.52 or delta == 0:
            continue

        if delta > 0 and not bull_regime:
            continue
        if delta < 0 and not bear_regime:
            continue

        net_flow = (buy_v[i] - sell_v[i]) / max(1.0, vols[i])
        dii = max(-0.99, min(0.99, (delta / 100.0) * (1.0 + vpin) + net_flow * 0.35))

        prev_low = np.min(lows[i - 16:i - 2])
        prev_high = np.max(highs[i - 16:i - 2])
        ict_bonus = 0.0
        if lows[i - 1] < prev_low and curr_px > prev_low and curr_px <= poc and delta > 0:
            ict_bonus = 14.0
        elif highs[i - 1] > prev_high and curr_px < prev_high and curr_px >= poc and delta < 0:
            ict_bonus = 14.0
        elif curr_px <= val and delta > 0:
            ict_bonus = 9.0
        elif curr_px >= vah and delta < 0:
            ict_bonus = 9.0

        if ict_bonus == 0.0:
            continue

        base_score = 50.0 + min(26.0, abs(delta) * 0.20 + abs(dii) * 24.0) + (vpin * 12.0) + ict_bonus
        conf = min(98.0, base_score)

        if conf >= CONFIDENCE_GATE:
            if len(rolling_pnls) >= 15:
                recent = rolling_pnls[-50:]
                w = [x for x in recent if x > 0]
                l = [abs(x) for x in recent if x < 0]
                p = len(w) / max(1, len(w) + len(l))
                b = (np.mean(w) if w else 1.0) / max(0.01, (np.mean(l) if l else 1.0))
                fk = p - ((1.0 - p) / max(0.1, b))
                hk = max(0.0025, min(MAX_RISK_PCT / 100.0, fk * 0.5))
            else:
                hk = 0.004

            atr = atr14[i]
            if is_btc:
                sl_dist = max(25000 * point, atr * 2.2)
            elif is_xau:
                sl_dist = max(350 * point, atr * 2.2)
            else:
                sl_dist = max(150 * point, atr * 2.2)

            t_dir = 1 if delta > 0 else -1
            t_entry = closes[i] + (spread_px if t_dir == 1 else 0.0)
            t_sl_dist = sl_dist
            t_sl = t_entry - sl_dist if t_dir == 1 else t_entry + sl_dist
            t_tp = t_entry + (sl_dist * 2.5) if t_dir == 1 else t_entry - (sl_dist * 2.5)
            t_risk_usd = equity * hk
            be_locked = False
            in_trade = True

    wins = [x for x in trades_pnl if x > 0]
    losses = [abs(x) for x in trades_pnl if x < 0]
    be_cnt = sum(1 for x in trades_pnl if x == 0.0)
    pf = sum(wins) / max(0.01, sum(losses))
    win_rate = (len(wins) / max(1, len(wins) + len(losses))) * 100.0
    net_pnl = equity - INITIAL_EQUITY

    return {
        "Symbol": symbol,
        "Trades": len(trades_pnl),
        "WinRate%": round(win_rate, 1),
        "BE_Locks": be_cnt,
        "ProfitFactor": round(pf, 2),
        "NetPnL($)": round(net_pnl, 2),
        "Return%": round((net_pnl / INITIAL_EQUITY) * 100.0, 1),
        "MaxDD%": round(max_dd_pct, 2),
        "FinalEq($)": round(equity, 2),
    }

if __name__ == "__main__":
    print("===================================================================================")
    print("  QUANTNEXUS v3.1 CALIBRATED WALK-FORWARD // ICT + VPIN + EMA REGIME + 1:2.5 RR    ")
    print("===================================================================================")
    if not mt5.initialize(path=VERIFIED_T1_PATH):
        raise SystemExit(1)

    results = [r for s in SYMBOLS if (r := backtest_calibrated(s))]
    mt5.shutdown()

    if results:
        df_res = pd.DataFrame(results)
        print("\n" + df_res.to_string(index=False))
        print("\n-----------------------------------------------------------------------------------")
        print(f"CALIBRATED FLEET: Total Trades = {df_res['Trades'].sum()} | Mean WinRate = {df_res['WinRate%'].mean():.1f}% | Mean PF = {df_res['ProfitFactor'].mean():.2f}")
        print(f"Combined Net Profit ($1k/slot): ${df_res['NetPnL($)'].sum():+,.2f} | Worst Max DD: {df_res['MaxDD%'].max():.2f}%")
        print("-----------------------------------------------------------------------------------")
