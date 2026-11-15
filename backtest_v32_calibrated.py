import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
MODEL_PATH = r"C:\Quant-Nexus-Eng\regime_classifier.pkl"
OUT_REPORT = Path(r"C:\Quant-Nexus-Eng\backtest_v32_2025_2026.json")

SYMBOLS = ["BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"]
MICRO_GATED = {"BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"}
FADE_SYMBOLS = {"XAUUSD", "BTCUSD"}

ASSET_THRESHOLDS = {
    "EURUSD": 0.70,
    "GBPUSD": 0.70,
    "USDJPY": 0.65,
    "US30":   0.68,
    "XAUUSD": 0.72,
    "BTCUSD": 0.72,
}

# Realistic Exness Standard/Pro contract dollar value per 1.0 price unit at 0.02L (0.05L US30)
LOT_AND_POINT_VAL = {
    "XAUUSD": (0.02, 100.0),    # $2.00 per $1.00 Gold move
    "BTCUSD": (0.02, 1.0),      # $0.02 per $1.00 BTC move
    "US30":   (0.05, 1.0),      # $0.05 per 1.0 pt US30 move
    "EURUSD": (0.02, 100000.0), # $2.00 per 10 pips
    "GBPUSD": (0.02, 100000.0),
    "USDJPY": (0.02, 625.0),
}

def load_ml_bundle():
    from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: F401
    bundle = joblib.load(MODEL_PATH)
    print(f"[ML SCHEMA] AUC={bundle.get('auc', 0):.4f} | Features={bundle.get('feature_names')}")
    return bundle

def prepare_symbol_df(symbol: str, bundle) -> pd.DataFrame | None:
    mt5.symbol_select(symbol, True)
    info = mt5.symbol_info(symbol)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 79920)
    if rates is None or len(rates) < 500 or not info:
        return None

    df = pd.DataFrame(rates)
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["tick_volume"].astype(float)

    prev_c = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
    atr14 = tr.rolling(14).mean()
    natr14 = (atr14 / c) * 100.0
    atr_base = tr.rolling(72).mean()

    rel_natr = natr14 / natr14.rolling(72, min_periods=10).mean()
    atr_exp_ratio = atr14 / atr_base

    log_hl = np.log(h / l) ** 2
    p_vol = np.sqrt((1.0 / (4.0 * np.log(2.0))) * log_hl.rolling(14).mean()) * np.sqrt(288 * 365)
    rel_p_vol = p_vol / p_vol.rolling(72, min_periods=10).mean()

    log_co = np.log(c / o) ** 2
    gk_term = 0.5 * log_hl - (2.0 * np.log(2.0) - 1.0) * log_co
    gk_vol = np.sqrt(np.maximum(0.0, gk_term.rolling(14).mean())) * np.sqrt(288 * 365)
    rel_gk_vol = gk_vol / gk_vol.rolling(72, min_periods=10).mean()

    bar_range = np.maximum(h - l, info.point)
    upper_wick = (h - np.maximum(o, c)) / bar_range
    lower_wick = (np.minimum(o, c) - l) / bar_range
    body_ratio = (c - o).abs() / bar_range
    rvol = v / v.rolling(24).mean()

    ret_1 = (c / c.shift(1)) - 1.0
    ret_3 = (c / c.shift(3)) - 1.0
    ret_12 = (c / c.shift(12)) - 1.0

    # Microstructure VPOC & 70% Value Area (rolling 12-bar M5 volume-weighted profile)
    typical = (h + l + c) / 3.0
    vpoc = (typical * v).rolling(12).sum() / np.maximum(v.rolling(12).sum(), 1.0)
    va_std = typical.rolling(12).std().fillna(atr14 * 0.5)
    vah = vpoc + va_std
    val = vpoc - va_std
    inside_poc_chop = (c - vpoc).abs() <= (atr14 * 0.45)

    # True Effort-vs-Result Delta Intensity Index (captures high-volume wick absorption)
    close_loc = ((c - l) / bar_range) * 2.0 - 1.0  # -1 at low, +1 at high
    signed_flow = close_loc * v
    roll_delta_pct = (signed_flow.rolling(3).sum() / np.maximum(v.rolling(3).sum(), 1.0)) * 100.0
    dii = (signed_flow / np.maximum(v, 1.0)) / (body_ratio + 0.15) * rvol.fillna(1.0)

    feat_df = pd.DataFrame({
        "rel_natr": rel_natr.fillna(1.0),
        "atr_expansion_ratio": atr_exp_ratio.fillna(1.0),
        "rel_parkinson": rel_p_vol.fillna(1.0),
        "rel_gk": rel_gk_vol.fillna(1.0),
        "upper_wick_ratio": upper_wick.fillna(0.0),
        "lower_wick_ratio": lower_wick.fillna(0.0),
        "body_ratio": body_ratio.fillna(0.5),
        "rvol": rvol.fillna(1.0),
        "ret_1": ret_1.fillna(0.0),
        "ret_3": ret_3.fillna(0.0),
        "ret_12": ret_12.fillna(0.0),
        "is_btc": 1 if symbol == "BTCUSD" else 0,
        "is_gold": 1 if symbol == "XAUUSD" else 0,
        "is_us30": 1 if symbol == "US30" else 0,
    })

    cols = bundle["feature_names"]
    df["p_exp"] = bundle["model"].predict_proba(feat_df[cols])[:, 1]
    df["atr14"] = atr14
    df["atr_exp"] = atr_exp_ratio
    df["rvol"] = rvol
    df["vpoc"] = vpoc
    df["vah"] = vah
    df["val"] = val
    df["inside_poc_chop"] = inside_poc_chop
    df["delta_pct"] = roll_delta_pct
    df["dii"] = dii
    df["point"] = info.point
    return df.iloc[80:].reset_index(drop=True)

def simulate_trade(df: pd.DataFrame, idx: int, side: str, entry: float, sl: float, tp: float, dollar_per_pt: float, spread_cost: float):
    risk = abs(entry - sl)
    if risk <= 0:
        return 0.0, idx + 1

    be_trigger = entry + (0.75 * risk) if side == "BUY" else entry - (0.75 * risk)
    harvest_trigger = entry + (1.40 * risk) if side == "BUY" else entry - (1.40 * risk)
    be_price = entry + (0.10 * risk) if side == "BUY" else entry - (0.10 * risk)

    cur_sl = sl
    harvested = False
    realized_pts = 0.0
    rem_weight = 1.0

    max_hold = min(idx + 96, len(df))
    for j in range(idx + 1, max_hold):
        bh = float(df["high"].iloc[j])
        bl = float(df["low"].iloc[j])
        if side == "BUY":
            if bl <= cur_sl:
                realized_pts += (cur_sl - entry) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j
            if not harvested and bh >= harvest_trigger:
                realized_pts += (harvest_trigger - entry) * 0.50
                rem_weight = 0.50
                harvested = True
                cur_sl = max(cur_sl, be_price)
            elif bh >= be_trigger:
                cur_sl = max(cur_sl, be_price)
            if bh >= tp:
                realized_pts += (tp - entry) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j
        else:
            if bh >= cur_sl:
                realized_pts += (entry - cur_sl) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j
            if not harvested and bl <= harvest_trigger:
                realized_pts += (entry - harvest_trigger) * 0.50
                rem_weight = 0.50
                harvested = True
                cur_sl = min(cur_sl, be_price)
            elif bl <= be_trigger:
                cur_sl = min(cur_sl, be_price)
            if bl <= tp:
                realized_pts += (entry - tp) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j

    final_c = float(df["close"].iloc[max_hold - 1])
    exit_pts = (final_c - entry) if side == "BUY" else (entry - final_c)
    realized_pts += exit_pts * rem_weight
    return (realized_pts * dollar_per_pt) - spread_cost, max_hold - 1

def run_sim(symbol_dfs: dict, upgraded: bool = True):
    trades = []
    for sym, df in symbol_dfs.items():
        lot, pt_val = LOT_AND_POINT_VAL[sym]
        dollar_per_pt = lot * pt_val
        thresh = ASSET_THRESHOLDS[sym]

        consec_losses = 0
        unlock_ts = 0
        i = 0
        n = len(df)

        while i < n - 15:
            row = df.iloc[i]
            ts = int(row["time"])
            dt = row["dt"]
            atr = float(row["atr14"])
            if np.isnan(atr) or atr <= 0:
                i += 1
                continue

            spread_cost = float(row["spread"]) * float(row["point"]) * dollar_per_pt

            if upgraded:
                if ts < unlock_ts:
                    i += 1
                    continue
                # London + NY Killzone Window (07:00 - 17:00 Server) & 13:25-13:40 News Blackout
                if not (7 <= dt.hour <= 17) or (dt.hour == 13 and 25 <= dt.minute <= 40):
                    i += 1
                    continue

            p_exp = float(row["p_exp"])
            atr_exp = float(row["atr_exp"])
            rvol = float(row["rvol"])
            close_p = float(row["close"])
            vpoc = float(row["vpoc"])
            vah = float(row["vah"])
            val = float(row["val"])
            chop = bool(row["inside_poc_chop"])
            delta_pct = float(row["delta_pct"])
            dii = float(row["dii"])

            taken = False
            # Expansion requires both ML regime probability AND true ATR/RVOL expansion
            exp_armed = (p_exp >= thresh) and (not upgraded or (atr_exp >= 1.15 and rvol >= 1.10))

            if exp_armed:
                allow_buy, allow_sell = True, True
                if upgraded and sym in MICRO_GATED:
                    if chop or abs(delta_pct) < 22.0:
                        allow_buy, allow_sell = False, False
                    elif delta_pct >= 22.0:
                        allow_sell = False
                    elif delta_pct <= -22.0:
                        allow_buy = False

                if allow_buy or allow_sell:
                    buf = atr * 1.1
                    sl_d = atr * 1.1 if upgraded else atr * 0.8
                    tp_d = atr * 2.8 if upgraded else atr * 2.5
                    buy_trig = close_p + buf
                    sell_trig = close_p - buf

                    for k in range(i + 1, min(i + 13, n - 5)):
                        bh = float(df["high"].iloc[k])
                        bl = float(df["low"].iloc[k])
                        news_slip = (atr * 0.8 * dollar_per_pt) if (not upgraded and df["dt"].iloc[k].hour == 13 and 29 <= df["dt"].iloc[k].minute <= 32) else 0.0

                        if allow_buy and bh >= buy_trig:
                            pnl, exit_idx = simulate_trade(df, k, "BUY", buy_trig, buy_trig - sl_d, buy_trig + tp_d, dollar_per_pt, spread_cost)
                            pnl -= news_slip
                            trades.append({"year": dt.year, "symbol": sym, "setup": "BREAKOUT_BUY", "pnl": pnl})
                            if pnl < -0.10:
                                consec_losses += 1
                                unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                            elif pnl > 0.10:
                                consec_losses = 0
                            i = exit_idx + 1
                            taken = True
                            break
                        elif allow_sell and bl <= sell_trig:
                            pnl, exit_idx = simulate_trade(df, k, "SELL", sell_trig, sell_trig + sl_d, sell_trig - tp_d, dollar_per_pt, spread_cost)
                            pnl -= news_slip
                            trades.append({"year": dt.year, "symbol": sym, "setup": "BREAKOUT_SELL", "pnl": pnl})
                            if pnl < -0.10:
                                consec_losses += 1
                                unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                            elif pnl > 0.10:
                                consec_losses = 0
                            i = exit_idx + 1
                            taken = True
                            break
                    if not taken:
                        i += 12
                        continue

            # Secondary Mode (V3.1): Nexus-OS DII Absorption Mean-Reversion at VAL/VAH -> VPOC
            if not taken and upgraded and sym in FADE_SYMBOLS and not chop:
                prev_c = float(df["close"].iloc[i - 1])
                if False and dii >= 2.5 and close_p >= prev_c and close_p <= val:
                    sl = val - (atr * 1.1)
                    tp = vpoc + ((vpoc - sl) * 1.2)
                    if abs(tp - close_p) / max(abs(close_p - sl), 1e-6) >= 1.3:
                        pnl, exit_idx = simulate_trade(df, i, "BUY", close_p, sl, tp, dollar_per_pt, spread_cost)
                        trades.append({"year": dt.year, "symbol": sym, "setup": "DII_FADE_BUY", "pnl": pnl})
                        consec_losses = (consec_losses + 1) if pnl < -0.10 else (0 if pnl > 0.10 else consec_losses)
                        if pnl < -0.10:
                            unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                        i = exit_idx + 1
                        continue
                elif dii <= -2.5 and close_p <= prev_c and close_p >= vah:
                    sl = vah + (atr * 1.1)
                    tp = vpoc - ((sl - vpoc) * 1.2)
                    if abs(close_p - tp) / max(abs(sl - close_p), 1e-6) >= 1.3:
                        pnl, exit_idx = simulate_trade(df, i, "SELL", close_p, sl, tp, dollar_per_pt, spread_cost)
                        trades.append({"year": dt.year, "symbol": sym, "setup": "DII_FADE_SELL", "pnl": pnl})
                        consec_losses = (consec_losses + 1) if pnl < -0.10 else (0 if pnl > 0.10 else consec_losses)
                        if pnl < -0.10:
                            unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                        i = exit_idx + 1
                        continue

            if not taken:
                i += 1
    return pd.DataFrame(trades)

def summarize(df_t: pd.DataFrame, label: str):
    if df_t.empty:
        return {"label": label, "trades": 0}
    wins = df_t[df_t["pnl"] > 0]
    losses = df_t[df_t["pnl"] < 0]
    gp = float(wins["pnl"].sum())
    gl = abs(float(losses["pnl"].sum()))
    cum = df_t["pnl"].cumsum()
    return {
        "label": label,
        "trades": int(len(df_t)),
        "win_rate_pct": round(len(wins) / len(df_t) * 100.0, 2),
        "net_pnl": round(float(df_t["pnl"].sum()), 2),
        "profit_factor": round(gp / gl if gl > 0 else 99.0, 2),
        "avg_win": round(float(wins["pnl"].mean()) if len(wins) else 0.0, 2),
        "avg_loss": round(float(losses["pnl"].mean()) if len(losses) else 0.0, 2),
        "max_dd_usd": round(float((cum.cummax() - cum).max()), 2),
        "by_year": df_t.groupby("year")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"),
        "by_symbol": df_t.groupby("symbol")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"),
        "by_setup": df_t.groupby("setup")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"),
    }

def main():
    mt5.initialize(path=TERMINAL, portable=False)
    bundle = load_ml_bundle()
    dfs = {s: prepare_symbol_df(s, bundle) for s in SYMBOLS}
    dfs = {k: v for k, v in dfs.items() if v is not None}

    r_base = summarize(run_sim(dfs, upgraded=False), "V2.1_BASELINE (24/5 Unfiltered)")
    r_v31 = summarize(run_sim(dfs, upgraded=True), "V3.2_CALIBRATED (6-Sym Micro + 0.70 FX Hurdle + Bearish VAH Fade + 1.1x ATR SL)")
    OUT_REPORT.write_text(json.dumps({"baseline": r_base, "v31_calibrated": r_v31}, indent=2), encoding="utf-8")

    for r in (r_base, r_v31):
        print("\n" + "-" * 92)
        print(f"MODEL: {r['label']}")
        print(f"Trades: {r['trades']} | Win Rate: {r.get('win_rate_pct')}% | Net PnL: ${r.get('net_pnl'):+,.2f} | "
              f"Profit Factor: {r.get('profit_factor')} | Max DD: ${r.get('max_dd_usd'):,.2f}")
        print(f"Avg Win: ${r.get('avg_win'):+.2f} | Avg Loss: ${r.get('avg_loss'):+.2f}")
        print("By Year :", r.get("by_year"))
        print("By Asset:", r.get("by_symbol"))
        print("By Setup:", r.get("by_setup"))
    mt5.shutdown()

if __name__ == "__main__":
    main()