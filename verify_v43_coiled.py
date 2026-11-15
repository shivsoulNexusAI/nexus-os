import numpy as np
import pandas as pd
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
SYMBOLS = ["XAUUSD", "US30", "BTCUSD"]
RISK_PER_TRADE_USD = 15.0

mt5.initialize(path=TERMINAL, portable=False)

all_trades = []
asset_summary = {}

for sym in SYMBOLS:
    mt5.symbol_select(sym, True)
    rates_m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 79920)
    info = mt5.symbol_info(sym)
    if rates_m5 is None or len(rates_m5) < 1500 or not info:
        continue

    point = info.point
    usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
    df_m5 = pd.DataFrame(rates_m5)
    df_m5["dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)

    df = df_m5.set_index("dt").resample("15min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum", "spread": "mean"
    }).dropna().reset_index()
    df["date"] = df["dt"].dt.date

    df_h1 = df_m5.set_index("dt").resample("1h").agg({"close": "last"}).dropna()
    df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
    df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
    df_h1["h1_strong_bull"] = (df_h1["close"] > df_h1["ema20"]) & (df_h1["ema20"] > df_h1["ema50"])

    df["h1_key"] = df["dt"].dt.floor("1h") - pd.Timedelta(hours=1)
    df = df.merge(df_h1[["h1_strong_bull"]], left_on="h1_key", right_index=True, how="left")
    df["h1_strong_bull"] = df["h1_strong_bull"].fillna(False)

    prev_c = df["close"].shift(1)
    tr = np.maximum(df["high"] - df["low"], np.maximum((df["high"] - prev_c).abs(), (df["low"] - prev_c).abs()))
    df["atr20"] = tr.rolling(20).mean().bfill()
    df["atr56"] = tr.rolling(56).mean().bfill()  # Exact 56-bar M15 ATR from run_prod_12m.py

    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["tick_volume"].astype(float)
    df["vpoc"] = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
    va_std = typical.rolling(16).std().fillna(df["atr20"])
    df["vah"] = df["vpoc"] + va_std

    bar_rng = np.maximum(df["high"] - df["low"], point)
    close_loc = ((df["close"] - df["low"]) / bar_rng) * 2.0 - 1.0
    df["delta_pct"] = ((close_loc * vol).rolling(4).sum() / np.maximum(vol.rolling(4).sum(), 1.0)) * 100.0
    body_ratio = (df["close"] - df["open"]).abs() / bar_rng
    df["dii"] = close_loc / (body_ratio + 0.15)

    trades = []
    consec_losses = 0
    skip_until_date = None

    for date, group in df.groupby("date"):
        if skip_until_date and date <= skip_until_date:
            continue
        if len(group) < 28:
            continue

        ref = group.iloc[:16]
        ref_high = float(ref["high"].max())
        ref_low = float(ref["low"].min())
        atr_box = float(ref["atr20"].iloc[-1])
        atr_56 = float(ref["atr56"].iloc[-1])
        if atr_box <= 0 or atr_56 <= 0:
            continue

        box_range = ref_high - ref_low
        # Mechanism A from run_prod_12m.py: Coiled Compression Gate (range <= 2.6 * ATR56)
        if box_range > (atr_56 * 2.6) or box_range < (atr_box * 0.6):
            continue

        buf_dist = atr_box * 0.40
        sl_dist = atr_box * 1.25
        t1_dist = sl_dist * 0.85   # +0.85R BE Lock
        t2_dist = sl_dist * 1.60   # +1.60R 50% Harvest
        t1_lock = sl_dist * 0.12
        t2_ratchet = sl_dist * 1.00  # Lock +1.0R floor on runner & let it ride uncapped to EOD!

        raw_lot = RISK_PER_TRADE_USD / max(sl_dist * usd_per_unit, 1e-6)
        lot = max(info.volume_min, min(0.25, round(raw_lot / info.volume_step) * info.volume_step))

        buy_stop = ref_high + buf_dist
        sell_stop = ref_low - buf_dist

        active_side = None
        entry_price = 0.0
        current_sl = 0.0
        t1_hit = False
        t2_hit = False
        rem_vol = lot
        pnl_accum = 0.0
        setup_type = ""
        spread_cost = 0.0

        for idx in range(16, len(group)):
            bar = group.iloc[idx]
            dt = bar["dt"]
            bh, bl, bc = float(bar["high"]), float(bar["low"]), float(bar["close"])
            delta_pct = float(bar["delta_pct"]) if not pd.isna(bar["delta_pct"]) else 0.0
            dii = float(bar["dii"]) if not pd.isna(bar["dii"]) else 0.0
            vah = float(bar["vah"]) if not pd.isna(bar["vah"]) else ref_high
            h1_bull = bool(bar["h1_strong_bull"])

            in_news = (dt.hour == 13 and 15 <= dt.minute <= 45)

            if active_side is None:
                if in_news or dt.hour >= 17:
                    continue
                spread_cost = float(bar["spread"]) * point * usd_per_unit * lot

                if delta_pct < 20.0 and bl <= sell_stop:
                    active_side = "SELL"
                    setup_type = "COILED_BREAK_SELL"
                    entry_price = sell_stop
                    current_sl = entry_price + sl_dist
                elif h1_bull and delta_pct >= 25.0 and bh >= buy_stop:
                    active_side = "BUY"
                    setup_type = "COILED_BREAK_BUY"
                    entry_price = buy_stop
                    current_sl = entry_price - sl_dist
                elif sym in ("XAUUSD", "BTCUSD") and dii <= -2.5 and bc >= vah and bc < buy_stop:
                    active_side = "SELL"
                    setup_type = "VAH_DII_FADE"
                    entry_price = bc
                    current_sl = buy_stop + (atr_box * 0.35)
                continue

            # Mechanism B from run_prod_12m.py: Uncapped Session Runner (no tight M15 candle choke)
            if active_side == "BUY":
                if bl <= current_sl:
                    pnl_accum += ((current_sl - entry_price) * usd_per_unit * rem_vol) - spread_cost
                    trades.append({"year": dt.year, "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
                    active_side = None
                    break
                if not t1_hit and bh >= (entry_price + t1_dist):
                    t1_hit = True
                    current_sl = max(current_sl, entry_price + t1_lock)
                if not t2_hit and bh >= (entry_price + t2_dist):
                    t2_hit = True
                    h_vol = round(rem_vol * 0.5, 2)
                    pnl_accum += t2_dist * usd_per_unit * h_vol
                    rem_vol = round(rem_vol - h_vol, 2)
                    current_sl = max(current_sl, entry_price + t2_ratchet)

            elif active_side == "SELL":
                if bh >= current_sl:
                    pnl_accum += ((entry_price - current_sl) * usd_per_unit * rem_vol) - spread_cost
                    trades.append({"year": dt.year, "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
                    active_side = None
                    break
                if not t1_hit and bl <= (entry_price - t1_dist):
                    t1_hit = True
                    current_sl = min(current_sl, entry_price - t1_lock)
                if not t2_hit and bl <= (entry_price - t2_dist):
                    t2_hit = True
                    h_vol = round(rem_vol * 0.5, 2)
                    pnl_accum += t2_dist * usd_per_unit * h_vol
                    rem_vol = round(rem_vol - h_vol, 2)
                    current_sl = min(current_sl, entry_price - t2_ratchet)

        # Honest EOD Session Close (no phantom vanishing trades!)
        if active_side is not None:
            eod_c = float(group.iloc[-1]["close"])
            diff = (eod_c - entry_price) if active_side == "BUY" else (entry_price - eod_c)
            pnl_accum += (diff * usd_per_unit * rem_vol) - spread_cost
            trades.append({"year": group.iloc[-1]["dt"].year, "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})

        if trades and trades[-1]["pnl"] < 0:
            consec_losses += 1
            if consec_losses >= 2:
                skip_until_date = date
                consec_losses = 0
        elif trades and trades[-1]["pnl"] > 0:
            consec_losses = 0

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

print(f"{'ASSET':<8} | {'TRADES':<7} | {'NET PNL':<12} | {'WIN RATE':<9} | {'PF':<6} | {'T2 HARV':<8} | {'AVG WIN':<9} | {'AVG LOSS'}")
print("-" * 108)
for sym, m in sorted(asset_summary.items(), key=lambda x: x[1]["net_pnl"], reverse=True):
    print(f"{sym:<8} | {m['trades']:<7} | ${m['net_pnl']:>+10.2f} | {m['win_rate']:>7.1f}% | {m['pf']:>5.2f} | {m['t2_harvests']:>8d} | ${m['avg_win']:>+7.2f} | ${m['avg_loss']:>+7.2f}")

print("=" * 108)
print(f"V4.3 SUMMARY (2025 - 2026) | Starting: $1,000.00 -> Ending: ${1000.0 + tot_pnl:,.2f} (ROI: +{tot_pnl/10.0:.1f}%)")
print(f"Total Setups: {len(df_all)} | Win Rate: {len(wins)/len(df_all)*100:.1f}% | TRUE Profit Factor: {tot_pf:.2f} | Max DD: ${max_dd:.2f}")
print("By Year :", df_all.groupby("year")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"))
print("By Setup:", df_all.groupby("setup")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"))
print("=" * 108)
mt5.shutdown()