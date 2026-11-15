import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
OUT_JSON = Path(r"C:\Quant-Nexus-Eng\final_v43_12m_certification.json")

END_DT = datetime(2026, 11, 12, 23, 59, tzinfo=timezone.utc)
START_DT = datetime(2025, 11, 12, 0, 0, tzinfo=timezone.utc)

CORE_TRIAD = ["XAUUSD", "US30", "BTCUSD"]
COMPRESSION_MULT = {"XAUUSD": 3.4, "US30": 2.6, "BTCUSD": 2.6}
INITIAL_CAPITAL = 1000.00
RISK_PER_TRADE_PCT = 0.013

def fetch_full_12m_m5(sym: str) -> pd.DataFrame:
    chunks = []
    cur = START_DT
    while cur < END_DT:
        nxt = min(cur + timedelta(days=30), END_DT)
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, cur, nxt)
        if rates is not None and len(rates) > 0:
            chunks.append(pd.DataFrame(rates))
        cur = nxt

    if not chunks:
        fallback = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 99999)
        if fallback is None or len(fallback) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(fallback)
    else:
        df = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df[(df["dt"] >= START_DT) & (df["dt"] <= END_DT)].reset_index(drop=True)
    return df

def main():
    if not mt5.initialize(path=TERMINAL, portable=False):
        print(f"[-] MT5 init failed: {mt5.last_error()}")
        return

    print("=" * 112)
    print("  QUANT-NEXUS V4.3 FINAL PRODUCTION: FULL 12-MONTH ROLLING CERTIFICATION (2025-11-12 -> 2026-11-12)")
    print("=" * 112)

    all_trades = []
    asset_summary = {}

    for sym in CORE_TRIAD:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        df_m5 = fetch_full_12m_m5(sym)
        if df_m5.empty or len(df_m5) < 2000 or not info:
            print(f"[-] Insufficient history for {sym}")
            continue

        point = info.point
        usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
        max_mult = COMPRESSION_MULT[sym]

        df = df_m5.set_index("dt").resample("15min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum", "spread": "mean"
        }).dropna().reset_index()
        df["date"] = df["dt"].dt.date

        # Prior closed H1 EMA(20/50) trend without lookahead
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
        df["atr56"] = tr.rolling(56).mean().bfill()

        # Rolling Microstructure Delta% & VPOC Chop Filter
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["tick_volume"].astype(float)
        vpoc = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
        va_std = typical.rolling(16).std().fillna(df["atr20"])
        df["inside_chop"] = (df["close"] - vpoc).abs() <= (0.20 * va_std)

        bar_rng = np.maximum(df["high"] - df["low"], point)
        close_loc = ((df["close"] - df["low"]) / bar_rng) * 2.0 - 1.0
        df["delta_pct"] = ((close_loc * vol).rolling(4).sum() / np.maximum(vol.rolling(4).sum(), 1.0)) * 100.0

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
            if box_range > (atr_56 * max_mult) or box_range < (atr_box * 0.6):
                continue

            buf_dist = atr_box * 0.40
            sl_dist = atr_box * 1.25
            t1_dist = sl_dist * 0.85   # +0.85R BE Lock
            t2_dist = sl_dist * 1.60   # +1.60R 50% Partial Harvest
            t1_lock = sl_dist * 0.12
            t2_ratchet = sl_dist * 1.00

            risk_usd = INITIAL_CAPITAL * RISK_PER_TRADE_PCT
            raw_lot = risk_usd / max(sl_dist * usd_per_unit, 1e-6)
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
                inside_chop = bool(bar["inside_chop"])
                h1_bull = bool(bar["h1_strong_bull"])

                # Exact 22:45 UTC EOD session close matching nexus_multi_straddle_daemon.py
                if active_side is not None and dt.hour == 22 and dt.minute >= 45:
                    diff = (bc - entry_price) if active_side == "BUY" else (entry_price - bc)
                    pnl_accum += (diff * usd_per_unit * rem_vol) - spread_cost
                    trades.append({"month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
                    active_side = None
                    break

                in_news = (dt.hour == 13 and 15 <= dt.minute <= 45)

                if active_side is None:
                    if in_news or dt.hour >= 17 or inside_chop:
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
                    continue

                if active_side == "BUY":
                    if bl <= current_sl:
                        pnl_accum += ((current_sl - entry_price) * usd_per_unit * rem_vol) - spread_cost
                        trades.append({"month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
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
                        trades.append({"month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
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

            if active_side is not None:
                eod_c = float(group.iloc[-1]["close"])
                diff = (eod_c - entry_price) if active_side == "BUY" else (entry_price - eod_c)
                pnl_accum += (diff * usd_per_unit * rem_vol) - spread_cost
                trades.append({"month": group.iloc[-1]["dt"].strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})

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
                "span": f"{df['dt'].iloc[0].strftime('%Y-%m-%d')} -> {df['dt'].iloc[-1].strftime('%Y-%m-%d')}",
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

    print(f"{'ASSET':<8} | {'HISTORY SPAN':<24} | {'TRADES':<6} | {'NET PNL':<11} | {'WIN RATE':<8} | {'PF':<5} | {'T2 HARV':<7} | {'AVG WIN':<8} | {'AVG LOSS'}")
    print("-" * 112)
    for sym, m in sorted(asset_summary.items(), key=lambda x: x[1]["net_pnl"], reverse=True):
        print(f"{sym:<8} | {m['span']:<24} | {m['trades']:<6} | ${m['net_pnl']:>+9.2f} | {m['win_rate']:>6.1f}% | {m['pf']:>5.2f} | {m['t2_harvests']:>7d} | ${m['avg_win']:>+6.2f} | ${m['avg_loss']:>+6.2f}")

    print("=" * 112)
    print(f"12-MONTH PORTFOLIO CERTIFICATION | Start: ${INITIAL_CAPITAL:,.2f} -> End: ${INITIAL_CAPITAL + tot_pnl:,.2f} (ROI: +{tot_pnl/10.0:.1f}%)")
    print(f"Total Setups: {len(df_all)} | Win Rate: {len(wins)/len(df_all)*100:.1f}% | TRUE Profit Factor: {tot_pf:.2f} | Max DD: ${max_dd:.2f} ({max_dd/10.0:.2f}%)")
    print("-" * 112)
    print("MONTHLY BREAKDOWN (2025-11 -> 2026-11):")
    m_grp = df_all.groupby("month")["pnl"].agg(trades="count", net_pnl="sum").round(2)
    for m_idx, row in m_grp.iterrows():
        print(f"  {m_idx} : {int(row['trades']):>3d} setups | Net PnL = ${row['net_pnl']:>+8.2f}")
    print("=" * 112)

    OUT_JSON.write_text(json.dumps({
        "certified_at": datetime.now(timezone.utc).isoformat(),
        "horizon": "2025-11-12 to 2026-11-12",
        "true_profit_factor": round(tot_pf, 2),
        "win_rate_pct": round(len(wins) / len(df_all) * 100.0, 1),
        "net_pnl_usd": round(tot_pnl, 2),
        "roi_pct": round(tot_pnl / 10.0, 1),
        "max_dd_usd": round(max_dd, 2),
        "assets": asset_summary,
    }, indent=2), encoding="utf-8")
    mt5.shutdown()

if __name__ == "__main__":
    main()