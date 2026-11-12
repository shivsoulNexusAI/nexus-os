from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278017866/terminal64.exe"
END_DT = datetime(2026, 11, 12, 23, 59, tzinfo=timezone.utc)
START_DT = datetime(2025, 11, 12, 0, 0, tzinfo=timezone.utc)

CORE_TRIAD = ["XAUUSD", "US30", "BTCUSD"]
COMPRESSION_MULT = {"XAUUSD": 3.4, "US30": 2.6, "BTCUSD": 2.6}
INITIAL_CAPITAL = 1000.00
BASE_RISK_PCT = 0.013

def fetch_full_12m_m5(sym: str) -> pd.DataFrame:
    chunks = []
    cur = START_DT
    while cur < END_DT:
        nxt = min(cur + timedelta(days=30), END_DT)
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, cur, nxt)
        if rates is not None and len(rates) > 0:
            chunks.append(pd.DataFrame(rates))
        cur = nxt
    df = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True) if chunks else pd.DataFrame()
    if df.empty:
        return df
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df[(df["dt"] >= START_DT) & (df["dt"] <= END_DT)].reset_index(drop=True)

mt5.initialize(path=TERMINAL, portable=False)
all_trades = []
asset_summary = {}

for sym in CORE_TRIAD:
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    df_m5 = fetch_full_12m_m5(sym)
    if df_m5.empty or not info:
        continue

    point = info.point
    usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
    max_mult = COMPRESSION_MULT[sym]

    df = df_m5.set_index("dt").resample("15min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum", "spread": "mean"
    }).dropna().reset_index()
    df["date"] = df["dt"].dt.date

    daily_hl = df.groupby("date").agg(day_high=("high", "max"), day_low=("low", "min")).shift(1)
    df = df.merge(daily_hl, on="date", how="left")

    df_h1 = df_m5.set_index("dt").resample("1h").agg({"close": "last"}).dropna()
    df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
    df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
    df_h1["h1_bull"] = (df_h1["close"] > df_h1["ema20"]) & (df_h1["ema20"] > df_h1["ema50"])
    df_h1["h1_bear"] = (df_h1["close"] < df_h1["ema20"]) & (df_h1["ema20"] < df_h1["ema50"])

    df["h1_key"] = df["dt"].dt.floor("1h") - pd.Timedelta(hours=1)
    df = df.merge(df_h1[["h1_bull", "h1_bear"]], left_on="h1_key", right_index=True, how="left")
    df["h1_bull"] = df["h1_bull"].fillna(False)
    df["h1_bear"] = df["h1_bear"].fillna(False)

    prev_c = df["close"].shift(1)
    tr = np.maximum(df["high"] - df["low"], np.maximum((df["high"] - prev_c).abs(), (df["low"] - prev_c).abs()))
    df["atr20"] = tr.rolling(20).mean().bfill()
    df["atr56"] = tr.rolling(56).mean().bfill()

    # STRICT SHIFT(1): Only closed prior M15 bars visible at decision time!
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["tick_volume"].astype(float)
    df["vol_ratio_prev"] = (vol / np.maximum(vol.rolling(20).mean(), 1.0)).shift(1).fillna(1.0)
    vpoc = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
    va_std = typical.rolling(16).std().fillna(df["atr20"])
    df["inside_chop_prev"] = ((df["close"] - vpoc).abs() <= (0.20 * va_std)).shift(1).fillna(False)

    bar_rng = np.maximum(df["high"] - df["low"], point)
    close_loc = ((df["close"] - df["low"]) / bar_rng) * 2.0 - 1.0
    df["delta_pct_prev"] = (((close_loc * vol).rolling(4).sum() / np.maximum(vol.rolling(4).sum(), 1.0)) * 100.0).shift(1).fillna(0.0)

    trades = []
    win_streak = 0
    consec_losses = 0
    skip_until_date = None

    active_side = None
    entry_price = current_sl = sl_dist_active = peak_gain_dist = rem_vol = pnl_accum = spread_cost = 0.0
    t1_hit = t2_hit = False
    setup_type = ""

    for date, group in df.groupby("date"):
        if len(group) < 28:
            continue

        box_ready = False
        buy_stop = sell_stop = sl_dist = 0.0
        if active_side is None:
            if skip_until_date and date <= skip_until_date:
                continue
            ref = group.iloc[:16]
            ref_high, ref_low = float(ref["high"].max()), float(ref["low"].min())
            atr_box, atr_56 = float(ref["atr20"].iloc[-1]), float(ref["atr56"].iloc[-1])
            if atr_box > 0 and atr_56 > 0 and (atr_box * 0.6) <= (ref_high - ref_low) <= (atr_56 * max_mult):
                buf_dist = atr_box * 0.40
                sl_dist = atr_box * 1.25
                buy_stop = ref_high + buf_dist
                sell_stop = ref_low - buf_dist
                box_ready = True

        for idx in range(16, len(group)):
            bar = group.iloc[idx]
            dt = bar["dt"]
            bh, bl, bc = float(bar["high"]), float(bar["low"]), float(bar["close"])
            delta_pct = float(bar["delta_pct_prev"])
            inside_chop = bool(bar["inside_chop_prev"])
            h1_bull, h1_bear = bool(bar["h1_bull"]), bool(bar["h1_bear"])
            vol_ratio = float(bar["vol_ratio_prev"])
            pdh = float(bar["day_high"]) if not pd.isna(bar["day_high"]) else 1e12
            pdl = float(bar["day_low"]) if not pd.isna(bar["day_low"]) else -1e12

            if active_side is not None and not t2_hit and dt.hour == 22 and dt.minute >= 45:
                diff = (bc - entry_price) if active_side == "BUY" else (entry_price - bc)
                pnl_accum += (diff * usd_per_unit * rem_vol) - spread_cost
                trades.append({"month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
                active_side = None
                break

            in_news = (dt.hour == 13 and 15 <= dt.minute <= 45)
            in_killzone = (7 <= dt.hour <= 15)

            just_entered = False
            if active_side is None:
                if not box_ready or in_news or not in_killzone or inside_chop or vol_ratio < 1.15:
                    continue

                scale = 1.35 if win_streak >= 1 else 1.0
                risk_usd = INITIAL_CAPITAL * BASE_RISK_PCT * scale
                raw_lot = risk_usd / max(sl_dist * usd_per_unit, 1e-6)
                lot = max(info.volume_min, min(0.30, round(raw_lot / info.volume_step) * info.volume_step))
                spread_cost = float(bar["spread"]) * point * usd_per_unit * lot

                pdh_clear = (pdh <= buy_stop) or ((pdh - buy_stop) >= sl_dist * 0.90)
                pdl_clear = (pdl >= sell_stop) or ((sell_stop - pdl) >= sl_dist * 0.90)

                if h1_bull and delta_pct >= 18.0 and pdh_clear and bh >= buy_stop:
                    active_side = "BUY"
                    setup_type = "V44_STRICT_BUY"
                    entry_price = buy_stop
                    sl_dist_active = sl_dist
                    current_sl = entry_price - sl_dist_active
                    t1_hit = t2_hit = False
                    peak_gain_dist = 0.0
                    rem_vol = lot
                    pnl_accum = 0.0
                    box_ready = False
                    just_entered = True
                elif h1_bear and delta_pct <= -18.0 and pdl_clear and bl <= sell_stop:
                    active_side = "SELL"
                    setup_type = "V44_STRICT_SELL"
                    entry_price = sell_stop
                    sl_dist_active = sl_dist
                    current_sl = entry_price + sl_dist_active
                    t1_hit = t2_hit = False
                    peak_gain_dist = 0.0
                    rem_vol = lot
                    pnl_accum = 0.0
                    box_ready = False
                    just_entered = True
                else:
                    continue

            t1_dist = sl_dist_active * 0.85
            t2_dist = sl_dist_active * 1.60

            # Conservative SL-first check even on entry candle
            if active_side == "BUY":
                if bl <= current_sl:
                    pnl_accum += ((current_sl - entry_price) * usd_per_unit * rem_vol) - spread_cost
                    trades.append({"month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
                    win_streak = (win_streak + 1) if pnl_accum > 0 else 0
                    consec_losses = 0 if pnl_accum > 0 else (consec_losses + 1)
                    if consec_losses >= 2:
                        skip_until_date = date
                        consec_losses = 0
                    active_side = None
                    break
                if not just_entered:
                    gain_now = bh - entry_price
                    peak_gain_dist = max(peak_gain_dist, gain_now)
                    if not t1_hit and gain_now >= t1_dist:
                        t1_hit = True
                        current_sl = max(current_sl, entry_price + (sl_dist_active * 0.12))
                    if not t2_hit and gain_now >= t2_dist:
                        t2_hit = True
                        h_vol = round(rem_vol * 0.5, 2)
                        pnl_accum += t2_dist * usd_per_unit * h_vol
                        rem_vol = round(rem_vol - h_vol, 2)
                        current_sl = max(current_sl, entry_price + (sl_dist_active * 1.05))
                    elif t2_hit and peak_gain_dist >= (sl_dist_active * 2.20):
                        lock_sl = entry_price + (peak_gain_dist * 0.65)
                        if lock_sl > current_sl:
                            current_sl = lock_sl

            elif active_side == "SELL":
                if bh >= current_sl:
                    pnl_accum += ((entry_price - current_sl) * usd_per_unit * rem_vol) - spread_cost
                    trades.append({"month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
                    win_streak = (win_streak + 1) if pnl_accum > 0 else 0
                    consec_losses = 0 if pnl_accum > 0 else (consec_losses + 1)
                    if consec_losses >= 2:
                        skip_until_date = date
                        consec_losses = 0
                    active_side = None
                    break
                if not just_entered:
                    gain_now = entry_price - bl
                    peak_gain_dist = max(peak_gain_dist, gain_now)
                    if not t1_hit and gain_now >= t1_dist:
                        t1_hit = True
                        current_sl = min(current_sl, entry_price - (sl_dist_active * 0.12))
                    if not t2_hit and gain_now >= t2_dist:
                        t2_hit = True
                        h_vol = round(rem_vol * 0.5, 2)
                        pnl_accum += t2_dist * usd_per_unit * h_vol
                        rem_vol = round(rem_vol - h_vol, 2)
                        current_sl = min(current_sl, entry_price - (sl_dist_active * 1.05))
                    elif t2_hit and peak_gain_dist >= (sl_dist_active * 2.20):
                        lock_sl = entry_price - (peak_gain_dist * 0.65)
                        if lock_sl < current_sl:
                            current_sl = lock_sl

    if active_side is not None:
        last_c = float(df.iloc[-1]["close"])
        diff = (last_c - entry_price) if active_side == "BUY" else (entry_price - last_c)
        pnl_accum += (diff * usd_per_unit * rem_vol) - spread_cost
        trades.append({"month": df.iloc[-1]["dt"].strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})

    if trades:
        df_s = pd.DataFrame(trades)
        wins = df_s[df_s["pnl"] > 0]["pnl"]
        losses = df_s[df_s["pnl"] <= 0]["pnl"]
        pf = float(wins.sum()) / abs(float(losses.sum())) if len(losses) else 99.0
        asset_summary[sym] = {
            "trades": len(df_s), "net_pnl": round(float(df_s["pnl"].sum()), 2),
            "win_rate": round(len(wins) / len(df_s) * 100.0, 1), "pf": round(pf, 2),
            "t2_harvests": int(df_s["t2"].sum()),
            "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 2),
            "avg_loss": round(float(losses.mean()) if len(losses) else 0.0, 2),
        }
        all_trades.extend(trades)

df_all = pd.DataFrame(all_trades)
wins = df_all[df_all["pnl"] > 0]["pnl"]
losses = df_all[df_all["pnl"] <= 0]["pnl"]
tot_pnl = float(df_all["pnl"].sum())
tot_pf = float(wins.sum()) / abs(float(losses.sum()))
cum = df_all["pnl"].cumsum()
max_dd = float((cum.cummax() - cum).max())

print("=" * 114)
print("  STRICT ZERO-LOOKAHEAD V4.4 CERTIFICATION (SHIFTED CLOSED BARS + CONSERVATIVE ENTRY-BAR SL CHECK)")
print("=" * 114)
print(f"{'ASSET':<8} | {'TRADES':<7} | {'NET PNL':<12} | {'WIN RATE':<9} | {'PF':<6} | {'T2 HARV':<8} | {'AVG WIN':<9} | {'AVG LOSS'}")
print("-" * 114)
for sym, m in sorted(asset_summary.items(), key=lambda x: x[1]["net_pnl"], reverse=True):
    print(f"{sym:<8} | {m['trades']:<7} | ${m['net_pnl']:>+10.2f} | {m['win_rate']:>7.1f}% | {m['pf']:>5.2f} | {m['t2_harvests']:>8d} | ${m['avg_win']:>+7.2f} | ${m['avg_loss']:>+7.2f}")
print("=" * 114)
print(f"STRICT V4.4 RESULT | Start: $1,000.00 -> End: ${1000.0 + tot_pnl:,.2f} (ROI: +{tot_pnl/10.0:.1f}%)")
print(f"Total Setups: {len(df_all)} | Win Rate: {len(wins)/len(df_all)*100:.1f}% | STRICT TRUE Profit Factor: {tot_pf:.2f} | Max DD: ${max_dd:.2f} ({max_dd/10.0:.2f}%)")
print("=" * 114)
mt5.shutdown()