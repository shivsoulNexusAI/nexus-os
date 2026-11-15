import json
import numpy as np
import pandas as pd
from pathlib import Path
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
OUT_REPORT = Path(r"C:\Quant-Nexus-Eng\backtest_v40_6asset_atr.json")

SYMBOLS = {
    "XAUUSD": 0.02,
    "US30":   0.05,
    "BTCUSD": 0.02,
    "EURUSD": 0.02,
    "GBPUSD": 0.02,
    "USDJPY": 0.02,
}

def main():
    if not mt5.initialize(path=TERMINAL, portable=False):
        print(f"[-] MT5 init failed: {mt5.last_error()}")
        return

    print("=" * 105)
    print("  QUANT-NEXUS V4.0 ATR-SCALED SESSION-BOX + MICROSTRUCTURE + UNCAPPED RUNNERS (ALL 6 ASSETS)")
    print("=" * 105)

    all_trades = []
    asset_summary = {}

    for sym, lot in SYMBOLS.items():
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
            "open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum"
        }).dropna().reset_index()
        df["date"] = df["dt"].dt.date

        # Rolling 20-bar M15 ATR (~5 hours volatility unit)
        prev_c = df["close"].shift(1)
        tr = np.maximum(df["high"] - df["low"], np.maximum((df["high"] - prev_c).abs(), (df["low"] - prev_c).abs()))
        df["atr"] = tr.rolling(20).mean().bfill()

        # Rolling Microstructure VPOC & Aggressor Delta
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["tick_volume"].astype(float)
        df["vpoc"] = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
        va_std = typical.rolling(16).std().fillna(df["atr"])
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

            # First 4 hours (16 M15 bars) define Asian accumulation box
            ref = group.iloc[:16]
            ref_high = float(ref["high"].max())
            ref_low = float(ref["low"].min())
            atr_box = float(ref["atr"].iloc[-1])
            if atr_box <= 0:
                continue

            box_range = ref_high - ref_low
            # Skip days where Asian range already exploded (> 6.5x M15 ATR)
            if box_range > (atr_box * 6.5) or box_range < (atr_box * 0.8):
                continue

            buf_dist = atr_box * 0.45
            sl_dist = atr_box * 1.35
            t1_dist = sl_dist * 1.00   # +1.0R BE Lock
            t2_dist = sl_dist * 2.00   # +2.0R 50% Harvest + Uncapped Runner Ratchet
            t1_lock = sl_dist * 0.15
            t2_ratchet = sl_dist * 1.15

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

            for idx in range(16, len(group)):
                bar = group.iloc[idx]
                dt = bar["dt"]
                bh, bl, bc = float(bar["high"]), float(bar["low"]), float(bar["close"])
                delta_pct = float(bar["delta_pct"]) if not pd.isna(bar["delta_pct"]) else 0.0
                dii = float(bar["dii"]) if not pd.isna(bar["dii"]) else 0.0
                vah = float(bar["vah"]) if not pd.isna(bar["vah"]) else ref_high

                in_news = (dt.hour == 13 and 15 <= dt.minute <= 45)

                if active_side is None:
                    if in_news or dt.hour >= 17:
                        continue

                    # Microstructure Delta Filter: block entries fighting strong opposite flow
                    allow_buy = delta_pct > -25.0
                    allow_sell = delta_pct < 25.0

                    if allow_buy and bh >= buy_stop:
                        active_side = "BUY"
                        setup_type = "BOX_BREAKOUT_BUY"
                        entry_price = buy_stop
                        current_sl = entry_price - sl_dist
                    elif allow_sell and bl <= sell_stop:
                        active_side = "SELL"
                        setup_type = "BOX_BREAKOUT_SELL"
                        entry_price = sell_stop
                        current_sl = entry_price + sl_dist
                    elif sym in ("XAUUSD", "BTCUSD") and dii <= -2.5 and bc >= vah and bc < buy_stop:
                        active_side = "SELL"
                        setup_type = "VAH_DII_FADE"
                        entry_price = bc
                        current_sl = buy_stop + (atr_box * 0.35)
                    continue

                if active_side == "BUY":
                    if bl <= current_sl:
                        pnl_accum += (current_sl - entry_price) * usd_per_unit * rem_vol
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
                        rem_vol -= h_vol
                        current_sl = max(current_sl, entry_price + t2_ratchet)
                    elif t2_hit and idx >= 18:
                        trail_sl = min(float(group.iloc[idx - 1]["low"]), float(group.iloc[idx - 2]["low"])) - (atr_box * 0.25)
                        if trail_sl > current_sl:
                            current_sl = trail_sl

                elif active_side == "SELL":
                    if bh >= current_sl:
                        pnl_accum += (entry_price - current_sl) * usd_per_unit * rem_vol
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
                        rem_vol -= h_vol
                        current_sl = min(current_sl, entry_price - t2_ratchet)
                    elif t2_hit and idx >= 18:
                        trail_sl = max(float(group.iloc[idx - 1]["high"]), float(group.iloc[idx - 2]["high"])) + (atr_box * 0.25)
                        if trail_sl < current_sl:
                            current_sl = trail_sl

            if active_side is not None:
                eod_c = float(group.iloc[-1]["close"])
                diff = (eod_c - entry_price) if active_side == "BUY" else (entry_price - eod_c)
                pnl_accum += diff * usd_per_unit * rem_vol
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
            gp = float(wins.sum())
            gl = abs(float(losses.sum()))
            pf = gp / gl if gl > 0 else 99.0
            asset_summary[sym] = {
                "trades": len(df_s),
                "net_pnl": round(float(df_s["pnl"].sum()), 2),
                "win_rate": round(len(wins) / len(df_s) * 100.0, 1),
                "pf": round(pf, 2),
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
    print("-" * 105)
    for sym, m in sorted(asset_summary.items(), key=lambda x: x[1]["net_pnl"], reverse=True):
        print(f"{sym:<8} | {m['trades']:<7} | ${m['net_pnl']:>+10.2f} | {m['win_rate']:>7.1f}% | {m['pf']:>5.2f} | {m['t2_harvests']:>8d} | ${m['avg_win']:>+7.2f} | ${m['avg_loss']:>+7.2f}")

    print("=" * 105)
    print(f"PORTFOLIO SUMMARY (2025 - 2026) | Starting Capital: $1,000.00 -> Ending: ${1000.0 + tot_pnl:,.2f} (ROI: +{tot_pnl/10.0:.1f}%)")
    print(f"Total Setups: {len(df_all)} | Win Rate: {len(wins)/len(df_all)*100:.1f}% | Profit Factor: {tot_pf:.2f} | Max DD: ${max_dd:.2f}")
    print("By Year :", df_all.groupby("year")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"))
    print("By Setup:", df_all.groupby("setup")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"))
    print("=" * 105)

    OUT_REPORT.write_text(json.dumps({"portfolio_pf": round(tot_pf, 2), "net_pnl": round(tot_pnl, 2), "max_dd": round(max_dd, 2), "assets": asset_summary}, indent=2), encoding="utf-8")
    mt5.shutdown()

if __name__ == "__main__":
    main()