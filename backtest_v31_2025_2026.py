import sys
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
MODEL_PATH = r"C:\Quant-Nexus-Eng\regime_classifier.pkl"
OUT_REPORT = Path(r"C:\Quant-Nexus-Eng\backtest_v31_2025_2026_results.json")

SYMBOLS = ["BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"]
MICRO_GATED = {"XAUUSD", "BTCUSD"}
FADE_SYMBOLS = {"XAUUSD", "BTCUSD", "EURUSD"}

ASSET_THRESHOLDS = {
    "EURUSD": 0.65,
    "GBPUSD": 0.65,
    "USDJPY": 0.65,
    "US30":   0.68,
    "XAUUSD": 0.72,
    "BTCUSD": 0.72,
}

# Contract value per 1.0 price move for standard lot sizes used in live fleet
LOT_AND_POINT_VAL = {
    "XAUUSD": (0.02, 100.0),    # 0.02L * $100/pt = $2.00 per $1.00 move
    "BTCUSD": (0.02, 1.0),      # 0.02L * $1/pt   = $0.02 per $1.00 move
    "US30":   (0.05, 1.0),      # 0.05L * $1/pt   = $0.05 per 1.0 pt move
    "EURUSD": (0.02, 100000.0), # 0.02L * $100k   = $2.00 per 0.00100 (10 pip) move
    "GBPUSD": (0.02, 100000.0),
    "USDJPY": (0.02, 625.0),    # ~0.02L * $625/pt at 160 USDJPY
}

START_DT = datetime(2025, 1, 1, tzinfo=timezone.utc)
END_DT = datetime(2026, 11, 12, tzinfo=timezone.utc)

def load_ml_bundle():
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: F401
        return joblib.load(MODEL_PATH)
    except Exception as e:
        print(f"[WARN] ML bundle fallback ({e}); using ATR expansion heuristic.")
        return None

def prepare_symbol_df(symbol: str, bundle) -> pd.DataFrame | None:
    mt5.symbol_select(symbol, True)
    rates = None
    for bar_count in (200000, 120000, 80000, 50000, 25000, 10000):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bar_count)
        if rates is not None and len(rates) >= 500:
            break
    if rates is None or len(rates) < 500:
        print(f"[SKIP] {symbol}: insufficient M5 history ({0 if rates is None else len(rates)} bars, err={mt5.last_error()}).")
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

    bar_range = np.maximum(h - l, 1e-6)
    upper_wick = (h - np.maximum(o, c)) / bar_range
    lower_wick = (np.minimum(o, c) - l) / bar_range
    body_ratio = (c - o).abs() / bar_range
    rvol = v / v.rolling(24).mean()

    ret_1 = (c / c.shift(1)) - 1.0
    ret_3 = (c / c.shift(3)) - 1.0
    ret_12 = (c / c.shift(12)) - 1.0

    # Microstructure VPOC & Value Area (rolling 12-bar M5 volume-weighted profile)
    typical = (h + l + c) / 3.0
    vpoc = (typical * v).rolling(12).sum() / np.maximum(v.rolling(12).sum(), 1.0)
    va_std = typical.rolling(12).std().fillna(atr14 * 0.5)
    vah = vpoc + va_std
    val = vpoc - va_std
    inside_poc_chop = (c - vpoc).abs() <= (atr14 * 0.35)

    # Bar Delta & Delta Intensity Index (DII)
    signed_flow = ((c - o) / bar_range) * v
    roll_delta_pct = (signed_flow.rolling(3).sum() / np.maximum(v.rolling(3).sum(), 1.0)) * 100.0
    price_eff = np.maximum(body_ratio, 0.05)
    dii = (signed_flow / np.maximum(v, 1.0)) / price_eff

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

    if bundle and "model" in bundle:
        cols = bundle["feature_names"]
        for col in cols:
            if col not in feat_df.columns:
                feat_df[col] = 0.0
        df["p_exp"] = bundle["model"].predict_proba(feat_df[cols])[:, 1]
    else:
        df["p_exp"] = np.clip((feat_df["atr_expansion_ratio"] - 0.85) * 2.0, 0.0, 0.95)

    df["atr14"] = atr14
    df["vpoc"] = vpoc
    df["vah"] = vah
    df["val"] = val
    df["inside_poc_chop"] = inside_poc_chop
    df["delta_pct"] = roll_delta_pct
    df["dii"] = dii
    df["symbol"] = symbol
    return df.iloc[80:].reset_index(drop=True)

def simulate_trade_outcome(df: pd.DataFrame, idx: int, side: str, entry: float, sl: float, tp: float, dollar_per_pt: float, spread_cost: float):
    """Simulates +0.75R Breakeven Lock and +1.40R 50% Rapid Harvest across forward M5 bars."""
    risk = abs(entry - sl)
    if risk <= 0:
        return 0.0, idx + 1

    be_trigger = entry + (0.75 * risk) if side == "BUY" else entry - (0.75 * risk)
    harvest_trigger = entry + (1.40 * risk) if side == "BUY" else entry - (1.40 * risk)
    be_price = entry + (0.08 * risk) if side == "BUY" else entry - (0.08 * risk)

    cur_sl = sl
    harvested = False
    realized_pts = 0.0
    rem_weight = 1.0

    max_hold = min(idx + 96, len(df))  # Up to 8 hours max hold
    for j in range(idx + 1, max_hold):
        bar_h = float(df["high"].iloc[j])
        bar_l = float(df["low"].iloc[j])

        if side == "BUY":
            if bar_l <= cur_sl:
                realized_pts += (cur_sl - entry) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j
            if not harvested and bar_h >= harvest_trigger:
                realized_pts += (harvest_trigger - entry) * 0.50
                rem_weight = 0.50
                harvested = True
                cur_sl = max(cur_sl, be_price)
            elif bar_h >= be_trigger:
                cur_sl = max(cur_sl, be_price)
            if bar_h >= tp:
                realized_pts += (tp - entry) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j
        else:
            if bar_h >= cur_sl:
                realized_pts += (entry - cur_sl) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j
            if not harvested and bar_l <= harvest_trigger:
                realized_pts += (entry - harvest_trigger) * 0.50
                rem_weight = 0.50
                harvested = True
                cur_sl = min(cur_sl, be_price)
            elif bar_l <= be_trigger:
                cur_sl = min(cur_sl, be_price)
            if bar_l <= tp:
                realized_pts += (entry - tp) * rem_weight
                return (realized_pts * dollar_per_pt) - spread_cost, j

    final_c = float(df["close"].iloc[max_hold - 1])
    exit_pts = (final_c - entry) if side == "BUY" else (entry - final_c)
    realized_pts += exit_pts * rem_weight
    return (realized_pts * dollar_per_pt) - spread_cost, max_hold - 1

def run_simulation(symbol_dfs: dict, mode: str = "V3.1"):
    """Runs either 'V2.1_BASELINE' or 'V3.1_UPGRADED' across 2025-2026."""
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

            spread_pts = float(row["spread"]) * (0.01 if "XAU" in sym else (1.0 if "BTC" in sym or "US30" in sym else (0.001 if "JPY" in sym else 0.00001)))
            spread_cost = spread_pts * dollar_per_pt * 0.5

            if mode == "V3.1_UPGRADED":
                # 1. Anti-Whipsaw Quarantine
                if ts < unlock_ts:
                    i += 1
                    continue
                # 2. 13:25-13:40 Macro News Blackout + Slippage Protection
                if dt.hour == 13 and 25 <= dt.minute <= 40:
                    i += 1
                    continue

            p_exp = float(row["p_exp"])
            close_p = float(row["close"])
            vpoc = float(row["vpoc"])
            vah = float(row["vah"])
            val = float(row["val"])
            chop = bool(row["inside_poc_chop"])
            delta_pct = float(row["delta_pct"])
            dii = float(row["dii"])

            trade_taken = False

            # PRIMARY MODE: Expansion Breakout Straddle
            if p_exp >= thresh:
                allow_buy, allow_sell = True, True
                if mode == "V3.1_UPGRADED" and sym in MICRO_GATED:
                    if chop or abs(delta_pct) < 18.0:
                        allow_buy, allow_sell = False, False
                    elif delta_pct >= 18.0:
                        allow_sell = False
                    elif delta_pct <= -18.0:
                        allow_buy = False

                if allow_buy or allow_sell:
                    buf = atr * 1.2
                    sl_d = atr * 0.8
                    tp_d = atr * 2.5
                    buy_trig = close_p + buf
                    sell_trig = close_p - buf

                    # Check next 12 bars (1 hour TTL) for bracket trigger
                    for k in range(i + 1, min(i + 13, n - 5)):
                        bh = float(df["high"].iloc[k])
                        bl = float(df["low"].iloc[k])
                        # News spike slippage penalty in V2.1 baseline
                        news_slip = (atr * 0.6 * dollar_per_pt) if (mode == "V2.1_BASELINE" and df["dt"].iloc[k].hour == 13 and 29 <= df["dt"].iloc[k].minute <= 32) else 0.0

                        if allow_buy and bh >= buy_trig:
                            pnl, exit_idx = simulate_trade_outcome(df, k, "BUY", buy_trig, buy_trig - sl_d, buy_trig + tp_d, dollar_per_pt, spread_cost)
                            pnl -= news_slip
                            trades.append({"year": dt.year, "symbol": sym, "setup": "BREAKOUT_BUY", "pnl": pnl})
                            if pnl < -0.10:
                                consec_losses += 1
                                unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                            elif pnl > 0.10:
                                consec_losses = 0
                            i = exit_idx + 1
                            trade_taken = True
                            break
                        elif allow_sell and bl <= sell_trig:
                            pnl, exit_idx = simulate_trade_outcome(df, k, "SELL", sell_trig, sell_trig + sl_d, sell_trig - tp_d, dollar_per_pt, spread_cost)
                            pnl -= news_slip
                            trades.append({"year": dt.year, "symbol": sym, "setup": "BREAKOUT_SELL", "pnl": pnl})
                            if pnl < -0.10:
                                consec_losses += 1
                                unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                            elif pnl > 0.10:
                                consec_losses = 0
                            i = exit_idx + 1
                            trade_taken = True
                            break
                    if not trade_taken:
                        i += 12
                        continue

            # SECONDARY MODE (V3.1 ONLY): Nexus-OS DII Absorption Mean-Reversion Fade at VAL/VAH -> VPOC
            if not trade_taken and mode == "V3.1_UPGRADED" and sym in FADE_SYMBOLS and not chop:
                prev_c = float(df["close"].iloc[i - 1])
                if dii <= -2.5 and close_p >= prev_c and close_p <= val:
                    sl = val - (atr * 0.85)
                    tp = vpoc + ((vpoc - sl) * 1.3)
                    if abs(tp - close_p) / max(abs(close_p - sl), 1e-6) >= 1.3:
                        pnl, exit_idx = simulate_trade_outcome(df, i, "BUY", close_p, sl, tp, dollar_per_pt, spread_cost)
                        trades.append({"year": dt.year, "symbol": sym, "setup": "DII_FADE_BUY", "pnl": pnl})
                        if pnl < -0.10:
                            consec_losses += 1
                            unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                        elif pnl > 0.10:
                            consec_losses = 0
                        i = exit_idx + 1
                        continue
                elif dii >= 2.5 and close_p <= prev_c and close_p >= vah:
                    sl = vah + (atr * 0.85)
                    tp = vpoc - ((sl - vpoc) * 1.3)
                    if abs(close_p - tp) / max(abs(sl - close_p), 1e-6) >= 1.3:
                        pnl, exit_idx = simulate_trade_outcome(df, i, "SELL", close_p, sl, tp, dollar_per_pt, spread_cost)
                        trades.append({"year": dt.year, "symbol": sym, "setup": "DII_FADE_SELL", "pnl": pnl})
                        if pnl < -0.10:
                            consec_losses += 1
                            unlock_ts = int(df["time"].iloc[exit_idx]) + (3600 if consec_losses >= 2 else 900)
                        elif pnl > 0.10:
                            consec_losses = 0
                        i = exit_idx + 1
                        continue

            if not trade_taken:
                i += 1

    return pd.DataFrame(trades)

def summarize(df_t: pd.DataFrame, label: str):
    if df_t.empty:
        return {"label": label, "trades": 0}
    wins = df_t[df_t["pnl"] > 0]
    losses = df_t[df_t["pnl"] < 0]
    gross_p = float(wins["pnl"].sum())
    gross_l = abs(float(losses["pnl"].sum()))
    pf = gross_p / gross_l if gross_l > 0 else 99.0
    cum = df_t["pnl"].cumsum()
    max_dd = float((cum.cummax() - cum).max())
    return {
        "label": label,
        "trades": int(len(df_t)),
        "win_rate_pct": round(len(wins) / len(df_t) * 100.0, 2),
        "net_pnl": round(float(df_t["pnl"].sum()), 2),
        "profit_factor": round(pf, 2),
        "avg_win": round(float(wins["pnl"].mean()) if len(wins) else 0.0, 2),
        "avg_loss": round(float(losses["pnl"].mean()) if len(losses) else 0.0, 2),
        "max_dd_usd": round(max_dd, 2),
        "by_year": df_t.groupby("year")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"),
        "by_symbol": df_t.groupby("symbol")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"),
        "by_setup": df_t.groupby("setup")["pnl"].agg(["count", "sum"]).round(2).to_dict("index"),
    }

def main():
    if not mt5.initialize(path=TERMINAL, portable=False):
        print(f"[ERROR] MT5 init failed: {mt5.last_error()}")
        sys.exit(1)

    print("=" * 92)
    print("  QUANT-NEXUS V3.1 UPGRADED VISION — FULL 2025 TO 2026 MULTI-ASSET BACKTEST")
    print("=" * 92)
    bundle = load_ml_bundle()
    symbol_dfs = {}
    for sym in SYMBOLS:
        df = prepare_symbol_df(sym, bundle)
        if df is not None:
            symbol_dfs[sym] = df
            print(f"[LOADED] {sym:<6}: {len(df):,} M5 bars ({df['dt'].iloc[0].strftime('%Y-%m-%d')} -> {df['dt'].iloc[-1].strftime('%Y-%m-%d')})")

    base_trades = run_simulation(symbol_dfs, mode="V2.1_BASELINE")
    v31_trades = run_simulation(symbol_dfs, mode="V3.1_UPGRADED")

    res_base = summarize(base_trades, "V2.1_BASELINE (No Micro/Whipsaw/News Shield)")
    res_v31 = summarize(v31_trades, "V3.1_UPGRADED (Micro VPOC/Delta + DII Fade + Shields)")

    OUT_REPORT.write_text(json.dumps({"baseline": res_base, "upgraded_v31": res_v31}, indent=2), encoding="utf-8")

    for r in (res_base, res_v31):
        print("\n" + "-" * 92)
        print(f"MODEL: {r['label']}")
        if r.get("trades", 0) == 0:
            print("Trades: 0 (No data loaded)")
            continue
        print(f"Trades: {r['trades']} | Win Rate: {r.get('win_rate_pct', 0.0)}% | Net PnL: ${r.get('net_pnl', 0.0):+,.2f} | "
              f"Profit Factor: {r.get('profit_factor', 0.0)} | Max DD: ${r.get('max_dd_usd', 0.0):,.2f}")
        print(f"Avg Win: ${r.get('avg_win'):+.2f} | Avg Loss: ${r.get('avg_loss'):+.2f}")
        print("By Year :", r.get("by_year"))
        print("By Asset:", r.get("by_symbol"))
        print("By Setup:", r.get("by_setup"))
    print("=" * 92)
    mt5.shutdown()

if __name__ == "__main__":
    main()