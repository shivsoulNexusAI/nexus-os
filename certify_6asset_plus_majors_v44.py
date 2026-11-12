import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278017866/terminal64.exe"
OUT_JSON = Path(r"C:\Quant-Nexus-Eng\audit_v44_focused_6plus_majors.json")

END_DT = datetime(2026, 11, 12, 23, 59, tzinfo=timezone.utc)
START_DT = datetime(2025, 11, 12, 0, 0, tzinfo=timezone.utc)

INITIAL_CAPITAL = 1000.00
BASE_RISK_PCT = 0.013

CORE_TRIAD = ["XAUUSD", "BTCUSD", "US30"]
MAJOR_FX = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "USDCHF", "NZDUSD"]
BASKET = CORE_TRIAD + MAJOR_FX


def resolve_symbol(base: str) -> str | None:
    if mt5.symbol_info(base) is not None:
        return base
    for s in (mt5.symbols_get() or []):
        if s.name.startswith(base) and len(s.name) <= len(base) + 2 and s.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
            return s.name
    return None


def fetch_full_12m_m5(sym: str) -> pd.DataFrame:
    chunks = []
    cur = START_DT
    while cur < END_DT:
        nxt = min(cur + timedelta(days=45), END_DT)
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, cur, nxt)
        if rates is not None and len(rates) > 0:
            chunks.append(pd.DataFrame(rates))
        cur = nxt
    if not chunks:
        fb = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 99999)
        df = pd.DataFrame(fb) if fb is not None else pd.DataFrame()
    else:
        df = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    if df.empty:
        return df
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df[(df["dt"] >= START_DT) & (df["dt"] <= END_DT)].reset_index(drop=True)


def run_symbol_v44(sym: str) -> tuple[dict | None, list[dict]]:
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    df_m5 = fetch_full_12m_m5(sym)
    if df_m5.empty or len(df_m5) < 2000 or not info:
        return None, []

    point = info.point
    usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
    max_mult = 3.4 if "XAU" in sym.upper() else 2.6

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

    # Strict shift(1) closed-bar indicators (Zero Intra-Bar Lookahead)
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
                trades.append({"dt": dt, "month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
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
                step = info.volume_step if info.volume_step > 0 else 0.01
                lot = max(info.volume_min, min(0.30, round(raw_lot / step) * step))
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

            if active_side == "BUY":
                if bl <= current_sl:
                    pnl_accum += ((current_sl - entry_price) * usd_per_unit * rem_vol) - spread_cost
                    trades.append({"dt": dt, "month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
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
                    trades.append({"dt": dt, "month": dt.strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
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
        trades.append({"dt": df.iloc[-1]["dt"], "month": df.iloc[-1]["dt"].strftime("%Y-%m"), "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})

    df_s = pd.DataFrame(trades)
    wins = df_s[df_s["pnl"] > 0]["pnl"]
    losses = df_s[df_s["pnl"] <= 0]["pnl"]
    pf = float(wins.sum()) / abs(float(losses.sum())) if len(losses) and abs(float(losses.sum())) > 0 else 99.0
    cum = df_s["pnl"].cumsum()
    max_dd = float((cum.cummax() - cum).max())

    return {
        "symbol": sym,
        "trades": len(df_s),
        "net_pnl": round(float(df_s["pnl"].sum()), 2),
        "win_rate": round(len(wins) / len(df_s) * 100.0, 1),
        "pf": round(pf, 2),
        "t2_harvests": int(df_s["t2"].sum()),
        "max_dd": round(max_dd, 2),
        "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 2),
        "avg_loss": round(float(losses.mean()) if len(losses) else 0.0, 2),
    }, trades


def summarize_portfolio(label: str, trade_list: list[dict]):
    df_p = pd.DataFrame(trade_list).sort_values("dt").reset_index(drop=True)
    wins = df_p[df_p["pnl"] > 0]["pnl"]
    losses = df_p[df_p["pnl"] <= 0]["pnl"]
    tot_pnl = float(df_p["pnl"].sum())
    tot_pf = float(wins.sum()) / abs(float(losses.sum()))
    cum = df_p["pnl"].cumsum()
    max_dd = float((cum.cummax() - cum).max())
    print(f"  {label:<38} | Setups: {len(df_p):>3d} | Win: {len(wins)/len(df_p)*100:>5.1f}% | TRUE PF: {tot_pf:>5.2f} | Net PnL: ${tot_pnl:>+9.2f} | Max DD: ${max_dd:>6.2f} ({max_dd/10.0:.2f}%)")


def main():
    if not mt5.initialize(path=TERMINAL, portable=False):
        print(f"[-] MT5 init failed: {mt5.last_error()}")
        return

    print("=" * 116)
    print("  QUANT-NEXUS V4.4 FOCUSED CERTIFICATION: CORE TRIAD + MAJOR CURRENCY PAIRS (2025-11-12 -> 2026-11-12)")
    print("=" * 116)
    print(f"{'GROUP':<8} | {'SYMBOL':<8} | {'TRADES':<6} | {'NET PNL':<10} | {'WIN %':<6} | {'TRUE PF':<7} | {'T2 HARV':<7} | {'MAX DD':<8} | {'AVG W / AVG L'}")
    print("-" * 116)

    summaries = []
    trades_by_base = {}
    for base in BASKET:
        sym = resolve_symbol(base)
        if not sym:
            continue
        s, tr = run_symbol_v44(sym)
        if s:
            s["base"] = base
            summaries.append(s)
            trades_by_base[base] = tr
            grp = "CORE" if base in CORE_TRIAD else "FX_MAJOR"
            wl_str = f"${s['avg_win']:+.2f} / ${s['avg_loss']:+.2f}"
            print(f"{grp:<8} | {sym:<8} | {s['trades']:<6} | ${s['net_pnl']:>+8.2f} | {s['win_rate']:>5.1f}% | {s['pf']:>7.2f} | {s['t2_harvests']:>7d} | ${s['max_dd']:>6.2f} | {wl_str}")

    print("=" * 116)
    print("PORTFOLIO COMBINATION COMPARISON (STRICT ZERO-LOOKAHEAD 12-MONTH):")
    core_trades = [t for b in CORE_TRIAD for t in trades_by_base.get(b, [])]
    top3_fx = sorted([s for s in summaries if s["base"] in MAJOR_FX], key=lambda x: x["pf"], reverse=True)[:3]
    top3_fx_bases = [s["base"] for s in top3_fx]
    six_asset_trades = core_trades + [t for b in top3_fx_bases for t in trades_by_base.get(b, [])]
    all_10_trades = [t for tr in trades_by_base.values() for t in tr]

    summarize_portfolio("1. Core Triad (XAU + BTC + US30)", core_trades)
    summarize_portfolio(f"2. 6-Asset (Core + {'+'.join(top3_fx_bases)})", six_asset_trades)
    summarize_portfolio("3. Full 10-Asset (Core + 7 Major FX)", all_10_trades)
    print("=" * 116)

    OUT_JSON.write_text(json.dumps({"rankings": summaries, "top3_fx": top3_fx_bases}, indent=2), encoding="utf-8")
    mt5.shutdown()


if __name__ == "__main__":
    main()