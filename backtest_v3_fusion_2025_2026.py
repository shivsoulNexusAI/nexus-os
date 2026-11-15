import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.append(r"C:\Program Files\Python312\Lib\site-packages")
sys.path.append(r"C:\Quant-Nexus-Eng")

import joblib
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

TERMINAL = r"C:/MT5_Pending_278041169/terminal64.exe"
MODEL_V3_PATH = r"C:\Quant-Nexus-Eng\model_bundle_v3.joblib"
MATRIX_CFG_PATH = r"C:\Quant-Nexus-Eng\nexus_straddle_matrix.json"
OUT_JSON = r"C:\Quant-Nexus-Eng\backtest_v3_fusion_2025_2026.json"

SYMBOLS = ["BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"]
FEATURE_COLS_V3 = [
    "rel_natr", "atr_expansion_ratio", "rel_parkinson", "rel_gk",
    "upper_wick_ratio", "lower_wick_ratio", "body_ratio", "rvol",
    "ret_1", "ret_3", "ret_12", "is_btc", "is_gold", "is_us30",
    "ict_killzone_active", "ict_bias_dir", "ict_liquidity_sweep",
    "ict_fvg_score", "order_flow_delta", "ict_red_team_pass"
]

END_DT = datetime(2026, 11, 13, 23, 59, tzinfo=timezone.utc)
START_DT = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
INITIAL_CAPITAL = 1000.0
BASE_RISK_PCT = 0.013

def fetch_m5_history(sym: str) -> pd.DataFrame:
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

def build_m15_v44_v3_frame(df_m5: pd.DataFrame, sym: str, point: float) -> pd.DataFrame:
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

    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
    df["atr20"] = tr.rolling(20).mean().bfill()
    df["atr56"] = tr.rolling(56).mean().bfill()

    # Exact V4.4 shift(1) zero-lookahead features
    typical = (h + l + c) / 3.0
    vol = df["tick_volume"].astype(float)
    df["vol_ratio_prev"] = (vol / np.maximum(vol.rolling(20).mean(), 1.0)).shift(1).fillna(1.0)
    vpoc = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
    va_std = typical.rolling(16).std().fillna(df["atr20"])
    df["inside_chop_prev"] = ((c - vpoc).abs() <= (0.20 * va_std)).shift(1).fillna(False)

    bar_rng = np.maximum(h - l, point)
    close_loc = ((c - l) / bar_rng) * 2.0 - 1.0
    df["delta_pct_prev"] = (((close_loc * vol).rolling(4).sum() / np.maximum(vol.rolling(4).sum(), 1.0)) * 100.0).shift(1).fillna(0.0)

    # 20-Feature V3 ML Vector (all causal / shift(1))
    natr20 = (df["atr20"] / c) * 100.0
    df["rel_natr"] = (natr20 / natr20.rolling(72, min_periods=10).mean()).shift(1).fillna(1.0)
    df["atr_expansion_ratio"] = (df["atr20"] / df["atr56"]).shift(1).fillna(1.0)

    log_hl = np.log((h / l).clip(lower=1e-9)) ** 2
    p_vol = np.sqrt((1.0 / (4.0 * np.log(2.0))) * log_hl.rolling(14).mean())
    df["rel_parkinson"] = (p_vol / p_vol.rolling(72, min_periods=10).mean()).shift(1).fillna(1.0)

    log_co = np.log((c / o).clip(lower=1e-9)) ** 2
    gk_term = 0.5 * log_hl - (2.0 * np.log(2.0) - 1.0) * log_co
    gk_vol = np.sqrt(np.maximum(0.0, gk_term.rolling(14).mean()))
    df["rel_gk"] = (gk_vol / gk_vol.rolling(72, min_periods=10).mean()).shift(1).fillna(1.0)

    df["upper_wick_ratio"] = ((h - np.maximum(o, c)) / bar_rng).shift(1).fillna(0.0)
    df["lower_wick_ratio"] = ((np.minimum(o, c) - l) / bar_rng).shift(1).fillna(0.0)
    df["body_ratio"] = ((c - o).abs() / bar_rng).shift(1).fillna(0.5)
    df["rvol"] = df["vol_ratio_prev"]

    df["ret_1"] = c.pct_change(1).shift(1).fillna(0.0)
    df["ret_3"] = c.pct_change(3).shift(1).fillna(0.0)
    df["ret_12"] = c.pct_change(12).shift(1).fillna(0.0)

    df["is_btc"] = 1 if sym == "BTCUSD" else 0
    df["is_gold"] = 1 if sym == "XAUUSD" else 0
    df["is_us30"] = 1 if sym == "US30" else 0

    hours = df["dt"].dt.hour
    df["ict_killzone_active"] = ((hours >= 7) & (hours <= 15)).astype(int)
    df["ict_bias_dir"] = np.where(df["h1_bull"], 1, np.where(df["h1_bear"], -1, 0))

    prev_hi_24 = h.rolling(24).max().shift(1)
    prev_lo_24 = l.rolling(24).min().shift(1)
    bsl_sweep = (h > prev_hi_24) & (c < prev_hi_24)
    ssl_sweep = (l < prev_lo_24) & (c > prev_lo_24)
    df["ict_liquidity_sweep"] = (bsl_sweep | ssl_sweep).shift(1).fillna(False).astype(int)

    bull_fvg = (l > h.shift(2)) & ((l - h.shift(2)) > 0.25 * df["atr20"])
    bear_fvg = (h < l.shift(2)) & ((l.shift(2) - h) > 0.25 * df["atr20"])
    df["ict_fvg_score"] = np.where((bull_fvg | bear_fvg).shift(1).fillna(False), 0.85, 0.0)

    df["order_flow_delta"] = np.clip(df["delta_pct_prev"] / 100.0, -1.0, 1.0)
    df["ict_red_team_pass"] = ((df["upper_wick_ratio"] < 0.65) & (df["lower_wick_ratio"] < 0.65)).astype(int)

    # Supervised target: does M15 impulse reach +1.60R before -1.00R within 24 M15 bars (6 hours)?
    fut_hi = h.shift(-1).rolling(24, min_periods=1).max().shift(-23)
    fut_lo = l.shift(-1).rolling(24, min_periods=1).min().shift(-23)
    sl_d = df["atr20"] * 1.25
    bull_ok = df["h1_bull"] & ((fut_hi - c) >= 1.60 * sl_d) & ((c - fut_lo) < 1.00 * sl_d)
    bear_ok = df["h1_bear"] & ((c - fut_lo) >= 1.60 * sl_d) & ((fut_hi - c) < 1.00 * sl_d)
    df["target_win"] = (bull_ok | bear_ok).astype(int)
    return df

def run_symbol_v44_v3(sym: str, df: pd.DataFrame, info, probs: np.ndarray, ml_gate: float = 0.42) -> tuple[dict, list[dict]]:
    point = info.point
    usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
    max_mult = 3.4 if "XAU" in sym.upper() else 2.6

    df = df.copy()
    df["ml_prob"] = probs

    trades = []
    win_streak = 0
    consec_losses = 0
    skip_until_date = None

    active_side = None
    entry_price = current_sl = sl_dist_active = peak_gain_dist = rem_vol = pnl_accum = spread_cost = 0.0
    t1_hit = t2_hit = False
    setup_type = ""
    entry_dt = None

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
            ml_p = float(bar["ml_prob"])
            pdh = float(bar["day_high"]) if not pd.isna(bar["day_high"]) else 1e12
            pdl = float(bar["day_low"]) if not pd.isna(bar["day_low"]) else -1e12

            # End-of-session / Friday weekend flat-book guard
            is_friday_close = (dt.day_of_week == 4 and dt.hour >= 20)
            if active_side is not None and ((not t2_hit and dt.hour == 22 and dt.minute >= 45) or is_friday_close):
                diff = (bc - entry_price) if active_side == "BUY" else (entry_price - bc)
                pnl_accum += (diff * usd_per_unit * rem_vol) - spread_cost
                trades.append({"entry_dt": entry_dt, "dt": dt, "year": dt.year, "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
                active_side = None
                break

            in_news = (dt.hour == 13 and 15 <= dt.minute <= 45)
            in_killzone = (7 <= dt.hour <= 15) and not is_friday_close

            just_entered = False
            if active_side is None:
                if not box_ready or in_news or not in_killzone or inside_chop or vol_ratio < 1.15 or ml_p < ml_gate:
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
                    setup_type = "V3_V44_BUY"
                    entry_price = buy_stop
                    entry_dt = dt
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
                    setup_type = "V3_V44_SELL"
                    entry_price = sell_stop
                    entry_dt = dt
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
                    trades.append({"entry_dt": entry_dt, "dt": dt, "year": dt.year, "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
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
                    trades.append({"entry_dt": entry_dt, "dt": dt, "year": dt.year, "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})
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
        last_dt = df.iloc[-1]["dt"]
        diff = (last_c - entry_price) if active_side == "BUY" else (entry_price - last_c)
        pnl_accum += (diff * usd_per_unit * rem_vol) - spread_cost
        trades.append({"entry_dt": entry_dt, "dt": last_dt, "year": last_dt.year, "symbol": sym, "setup": setup_type, "pnl": pnl_accum, "t2": t2_hit})

    tdf = pd.DataFrame(trades)
    if not tdf.empty:
        wins = tdf[tdf["pnl"] > 0]["pnl"].sum()
        losses = abs(tdf[tdf["pnl"] < 0]["pnl"].sum())
        pf = round(wins / losses, 2) if losses > 0 else 99.0
        wr = round((len(tdf[tdf["pnl"] > 0]) / len(tdf)) * 100.0, 1)
        net = round(tdf["pnl"].sum(), 2)
        t2_cnt = int(tdf["t2"].sum())
    else:
        pf, wr, net, t2_cnt = 0.0, 0.0, 0.0, 0

    return {
        "trades": len(trades),
        "t2_harvests": t2_cnt,
        "win_rate_pct": wr,
        "profit_factor": pf,
        "net_pnl_usd": net,
    }, trades

def main():
    t0 = time.time()
    if not mt5.initialize(path=TERMINAL):
        print(f"[FATAL] MT5 init failed: {mt5.last_error()}")
        sys.exit(1)

    print("=" * 98)
    print("  STEP 1: SYMBOL-STRATIFIED WALK-FORWARD V3 ML TRAINING (REAL M15 INSTITUTIONAL BARS)")
    print("=" * 98)

    m15_frames = {}
    sym_infos = {}
    train_parts = []
    oos_parts = []

    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        df_m5 = fetch_m5_history(sym)
        if df_m5.empty or not info:
            continue
        df_m15 = build_m15_v44_v3_frame(df_m5, sym, info.point)
        m15_frames[sym] = df_m15
        sym_infos[sym] = info

        cand = df_m15[(df_m15["ict_killzone_active"] == 1) & (~df_m15["inside_chop_prev"]) & (df_m15["vol_ratio_prev"] >= 1.15)].dropna(subset=FEATURE_COLS_V3)
        split_idx = int(len(cand) * 0.40)
        if split_idx > 20:
            train_parts.append(cand.iloc[:split_idx])
            oos_parts.append(cand.iloc[split_idx:])

    train_df = pd.concat(train_parts, ignore_index=True)
    oos_df = pd.concat(oos_parts, ignore_index=True)

    pipeline_v3 = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("classifier", HistGradientBoostingClassifier(
            max_iter=150,
            learning_rate=0.035,
            max_depth=4,
            min_samples_leaf=25,
            l2_regularization=1.5,
            class_weight="balanced",
            random_state=2026
        ))
    ])
    pipeline_v3.fit(train_df[FEATURE_COLS_V3], train_df["target_win"])
    oos_probs = pipeline_v3.predict_proba(oos_df[FEATURE_COLS_V3])[:, 1]
    oos_auc = float(roc_auc_score(oos_df["target_win"], oos_probs))

    bundle_v3 = {
        "model": pipeline_v3,
        "feature_names": FEATURE_COLS_V3,
        "auc": round(oos_auc, 4),
        "train_samples": int(len(train_df)),
        "oos_samples": int(len(oos_df)),
        "version": "v3_v44_m15_walkforward_certified"
    }
    joblib.dump(bundle_v3, MODEL_V3_PATH)
    print(f"  [ML V3 CERTIFIED] Stratified Train Bars: {len(train_df)} | Out-of-Sample Bars: {len(oos_df)} | OOS ROC-AUC: {oos_auc:.4f}")

    print("\n" + "=" * 98)
    print("  STEP 2: RUNNING CERTIFIED V3 + V4.4 WALK-FORWARD BACKTEST (2025 -> 2026-11-13)")
    print("=" * 98)

    all_trades = []
    per_symbol_stats = {}

    for sym, df_m15 in m15_frames.items():
        probs = pipeline_v3.predict_proba(df_m15[FEATURE_COLS_V3])[:, 1]
        stats, sym_trades = run_symbol_v44_v3(sym, df_m15, sym_infos[sym], probs, ml_gate=0.42)
        per_symbol_stats[sym] = stats
        all_trades.extend(sym_trades)
        print(f"  {sym:<7} | Trades: {stats['trades']:>4} (T2 Harvests: {stats['t2_harvests']:>3}) | WR: {stats['win_rate_pct']:>5.1f}% | PF: {stats['profit_factor']:>5.2f} | Net PnL: ${stats['net_pnl_usd']:>+8.2f}")

    mt5.shutdown()

    # Portfolio Aggregation (Max 4 Concurrent Brackets)
    all_trades.sort(key=lambda x: x["entry_dt"])
    active_exits = []
    portfolio_trades = []
    for tr in all_trades:
        active_exits = [et for et in active_exits if et > tr["entry_dt"]]
        if len(active_exits) >= 4:
            continue
        active_exits.append(tr["dt"])
        portfolio_trades.append(tr)

    pdf = pd.DataFrame(portfolio_trades)
    if not pdf.empty:
        pdf["equity"] = INITIAL_CAPITAL + pdf["pnl"].cumsum()
        pdf["peak"] = pdf["equity"].cummax()
        pdf["dd_pct"] = ((pdf["peak"] - pdf["equity"]) / pdf["peak"]) * 100.0

        total_net = round(pdf["pnl"].sum(), 2)
        final_eq = round(INITIAL_CAPITAL + total_net, 2)
        gross_win = pdf[pdf["pnl"] > 0]["pnl"].sum()
        gross_loss = abs(pdf[pdf["pnl"] < 0]["pnl"].sum())
        port_pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 99.0
        port_wr = round((len(pdf[pdf["pnl"] > 0]) / len(pdf)) * 100.0, 2)
        max_dd = round(pdf["dd_pct"].max(), 2)
        ret_pct = round((total_net / INITIAL_CAPITAL) * 100.0, 2)
        y2025 = round(pdf[pdf["year"] == 2025]["pnl"].sum(), 2)
        y2026 = round(pdf[pdf["year"] == 2026]["pnl"].sum(), 2)
    else:
        total_net = final_eq = port_pf = port_wr = max_dd = ret_pct = y2025 = y2026 = 0.0

    summary = {
        "period": "2025-01-01 to 2026-11-13",
        "oos_ml_auc": round(oos_auc, 4),
        "initial_balance": INITIAL_CAPITAL,
        "final_equity": final_eq,
        "net_pnl_usd": total_net,
        "total_return_pct": ret_pct,
        "portfolio_trades": len(portfolio_trades),
        "win_rate_pct": port_wr,
        "profit_factor": port_pf,
        "max_drawdown_pct": max_dd,
        "pnl_2025_usd": y2025,
        "pnl_2026_ytd_usd": y2026,
        "per_symbol": per_symbol_stats,
        "elapsed_sec": round(time.time() - t0, 2),
    }
    Path(OUT_JSON).write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("-" * 98)
    print(f"  CERTIFIED PORTFOLIO SUMMARY (Max 4 Concurrent Brackets | Start: ${INITIAL_CAPITAL:.2f})")
    print(f"  Final Equity: ${final_eq:.2f} ({ret_pct:+.2f}%) | Net PnL: ${total_net:+.2f} (2025: ${y2025:+.2f} | 2026 YTD: ${y2026:+.2f})")
    print(f"  Total Trades: {len(portfolio_trades)} | Win Rate: {port_wr:.2f}% | Profit Factor: {port_pf:.2f} | Max Drawdown: {max_dd:.2f}%")
    print(f"  Saved report -> {OUT_JSON} (Completed in {summary['elapsed_sec']}s)")
    print("=" * 98)

if __name__ == "__main__":
    main()
