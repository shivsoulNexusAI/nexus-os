# -*- coding: utf-8 -*-
"""
SHIVSOUL QUANTITATIVE DESK - DISPLACEMENT & IMBALANCE CONFIRMATION ENGINE
"""

import os
import joblib
import warnings
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

warnings.filterwarnings('ignore')

MODEL_PATH = "regime_model.joblib"
OUTPUT_REPORT = "backtest_performance_audit.csv"
BARS_TO_TEST = 15000
INITIAL_CAPITAL = 10000.0

ASSET_PARAMS = {
    "EURUSD": {"tp_mult": 1.6, "trail_trigger": 1.1, "risk_pct": 1.0},
    "GBPUSD": {"tp_mult": 1.6, "trail_trigger": 1.1, "risk_pct": 1.0},
    "USDJPY": {"tp_mult": 1.6, "trail_trigger": 1.1, "risk_pct": 0.75},
    "XAUUSD": {"tp_mult": 2.2, "trail_trigger": 1.25, "risk_pct": 0.5},
    "BTCUSD": {"tp_mult": 2.2, "trail_trigger": 1.25, "risk_pct": 0.5}
}

class DisplacementBacktester:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.params = ASSET_PARAMS.get(symbol, {"tp_mult": 1.8, "trail_trigger": 1.2, "risk_pct": 1.0})
        self.balance = INITIAL_CAPITAL
        self.trades = []
        self.open_pos = None

        self.gmm_data = None
        if os.path.exists(MODEL_PATH):
            try:
                self.gmm_data = joblib.load(MODEL_PATH)
            except Exception:
                pass

    def get_regime(self, window_df: pd.DataFrame) -> tuple[str, float]:
        if not self.gmm_data or len(window_df) < 75:
            return "CLEAN_TREND", 1.0

        tr = np.maximum(
            window_df["high"] - window_df["low"],
            np.maximum(
                abs(window_df["high"] - window_df["close"].shift(1)),
                abs(window_df["low"] - window_df["close"].shift(1))
            )
        )
        atr_fast = tr.rolling(14).mean().iloc[-1]
        atr_slow = tr.rolling(70).mean().iloc[-1]
        atr_ratio = atr_fast / (atr_slow + 1e-9)

        net_change = abs(window_df["close"].iloc[-1] - window_df["close"].iloc[-16])
        total_path = tr.iloc[-15:].sum()
        efficiency = net_change / (total_path + 1e-9)

        log_ret = np.log(window_df["close"].iloc[-1] / (window_df["close"].iloc[-2] + 1e-9))
        vol_15 = np.log(window_df["close"] / window_df["close"].shift(1)).iloc[-15:].std()
        if np.isnan(vol_15):
            vol_15 = 0.0001

        c_range = window_df["high"].iloc[-1] - window_df["low"].iloc[-1]
        c_body = abs(window_df["close"].iloc[-1] - window_df["open"].iloc[-1])
        wick_ratio = (c_range - c_body) / (c_range + 1e-9)

        feat_df = pd.DataFrame([[log_ret, vol_15, atr_ratio, efficiency, wick_ratio]], 
                               columns=["log_ret", "vol_15", "atr_ratio", "efficiency", "wick_ratio"])

        scaler = self.gmm_data["scaler"]
        gmm = self.gmm_data["model"]
        labels = self.gmm_data["cluster_labels"]

        X_scaled = scaler.transform(feat_df)
        probs = gmm.predict_proba(X_scaled)[0]
        cid = int(np.argmax(probs))
        regime = labels.get(cid, "RANGE_ACCUMULATION")

        mult = 0.0 if regime == "CHOP_VETO" else (1.0 if regime == "CLEAN_TREND" else 0.75)
        return regime, mult

    def run(self):
        mt5.symbol_select(self.symbol, True)
        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, BARS_TO_TEST)
        if rates is None or len(rates) < 500:
            return

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["close"].shift(1)),
                abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = df["tr"].rolling(14).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

        df["pool_high"] = df["high"].rolling(20).max().shift(2)
        df["pool_low"] = df["low"].rolling(20).min().shift(2)

        print(f"[*] Simulating {self.symbol} with Order-Flow Displacement Confirmation...")

        for i in range(200, len(df)):
            bar = df.iloc[i]
            cur_time = bar["time"]
            cur_close = bar["close"]
            cur_open = bar["open"]
            cur_high = bar["high"]
            cur_low = bar["low"]
            cur_atr = bar["atr"]
            cur_ema = bar["ema200"]

            # 1. Manage Active Positions
            if self.open_pos:
                pos = self.open_pos
                closed = False
                exit_price = 0.0
                outcome = ""

                trail_trigger_dist = self.params["trail_trigger"] * pos["sl_dist"]

                if pos["direction"] == "BUY":
                    if not pos["be_active"] and cur_high >= (pos["entry"] + trail_trigger_dist):
                        pos["sl"] = pos["entry"] + (0.1 * pos["sl_dist"])
                        pos["be_active"] = True

                    if cur_low <= pos["sl"]:
                        exit_price = pos["sl"]
                        outcome = "BREAKEVEN" if pos["be_active"] else "LOSS"
                        closed = True
                    elif cur_high >= pos["tp"]:
                        exit_price = pos["tp"]
                        outcome = "WIN"
                        closed = True

                elif pos["direction"] == "SELL":
                    if not pos["be_active"] and cur_low <= (pos["entry"] - trail_trigger_dist):
                        pos["sl"] = pos["entry"] - (0.1 * pos["sl_dist"])
                        pos["be_active"] = True

                    if cur_high >= pos["sl"]:
                        exit_price = pos["sl"]
                        outcome = "BREAKEVEN" if pos["be_active"] else "LOSS"
                        closed = True
                    elif cur_low <= pos["tp"]:
                        exit_price = pos["tp"]
                        outcome = "WIN"
                        closed = True

                if closed:
                    r_pnl = (exit_price - pos["entry"]) / pos["sl_dist"] if pos["direction"] == "BUY" else (pos["entry"] - exit_price) / pos["sl_dist"]
                    dollar_pnl = r_pnl * pos["dollar_risk"]
                    self.balance += dollar_pnl

                    self.trades.append({
                        "symbol": self.symbol,
                        "entry_time": pos["time"],
                        "exit_time": cur_time,
                        "direction": pos["direction"],
                        "regime": pos["regime"],
                        "entry_price": pos["entry"],
                        "exit_price": exit_price,
                        "outcome": outcome,
                        "r_multiple": round(r_pnl, 2),
                        "dollar_pnl": round(dollar_pnl, 2),
                        "balance_after": round(self.balance, 2)
                    })
                    self.open_pos = None

            # 2. Check for Sweep + Displacement Setup
            if not self.open_pos and cur_atr > 0:
                hour = cur_time.hour
                if hour < 7 or hour > 18:
                    continue

                p_high = bar["pool_high"]
                p_low = bar["pool_low"]
                signal_dir = None

                body_size = abs(cur_close - cur_open)
                # Displacement: candle body must be substantial (>= 60% of current ATR)
                has_displacement = body_size >= (0.60 * cur_atr)

                recent_min = df["low"].iloc[i-2:i+1].min()
                recent_max = df["high"].iloc[i-2:i+1].max()

                # Bullish: Trend anchor + Liquidity sweep + Strong bullish displacement candle
                if cur_close > cur_ema and recent_min < p_low and cur_close > p_low and cur_close > cur_open and has_displacement:
                    signal_dir = "BUY"
                    sl_dist = max(1.4 * cur_atr, abs(cur_close - recent_min) * 1.05)
                    sl = cur_close - sl_dist
                    tp = cur_close + (sl_dist * self.params["tp_mult"])

                # Bearish: Trend anchor + Liquidity sweep + Strong bearish displacement candle
                elif cur_close < cur_ema and recent_max > p_high and cur_close < p_high and cur_close < cur_open and has_displacement:
                    signal_dir = "SELL"
                    sl_dist = max(1.4 * cur_atr, abs(recent_max - cur_close) * 1.05)
                    sl = cur_close + sl_dist
                    tp = cur_close - (sl_dist * self.params["tp_mult"])

                if signal_dir:
                    window_80 = df.iloc[i-79 : i+1]
                    regime, risk_mult = self.get_regime(window_80)

                    if risk_mult > 0.0:
                        risk_pct = self.params["risk_pct"] * risk_mult
                        allocated_risk = self.balance * (risk_pct / 100.0)
                        self.open_pos = {
                            "time": cur_time,
                            "direction": signal_dir,
                            "regime": regime,
                            "entry": cur_close,
                            "sl": sl,
                            "tp": tp,
                            "sl_dist": sl_dist,
                            "dollar_risk": allocated_risk,
                            "be_active": False
                        }

    def metrics(self):
        if not self.trades:
            return {"Symbol": self.symbol, "Total Trades": 0, "Win %": 0.0, "BE %": 0.0, "Loss %": 0.0, "Profit Factor": 0.0, "Max DD %": 0.0, "SQN": 0.0, "Return %": 0.0}

        tdf = pd.DataFrame(self.trades)
        wins = tdf[tdf["outcome"] == "WIN"]
        losses = tdf[tdf["outcome"] == "LOSS"]
        bes = tdf[tdf["outcome"] == "BREAKEVEN"]

        gross_profit = wins["dollar_pnl"].sum()
        gross_loss = abs(losses["dollar_pnl"].sum())
        pf = round(gross_profit / (gross_loss + 1e-9), 2)

        tdf["peak"] = tdf["balance_after"].cummax()
        tdf["dd"] = (tdf["balance_after"] - tdf["peak"]) / tdf["peak"] * 100.0
        max_dd = round(abs(tdf["dd"].min()), 2)

        pnl = tdf["dollar_pnl"]
        sqn = round(np.sqrt(len(tdf)) * (pnl.mean() / (pnl.std() + 1e-9)), 2)
        ret = round(((self.balance - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100.0, 1)

        return {
            "Symbol": self.symbol,
            "Total Trades": len(tdf),
            "Win %": round(len(wins) / len(tdf) * 100, 1),
            "BE %": round(len(bes) / len(tdf) * 100, 1),
            "Loss %": round(len(losses) / len(tdf) * 100, 1),
            "Profit Factor": pf,
            "Max DD %": max_dd,
            "SQN": sqn,
            "Return %": ret
        }

def run_suite():
    if not mt5.initialize():
        print("[-] Error: MetaTrader 5 offline.")
        return

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
    summary = []
    all_trades = []

    print("\n=======================================================")
    print(" NEXUS INSTITUTIONAL AUDIT (Displacement + Imbalance) ")
    print("=======================================================\n")

    for s in symbols:
        bt = DisplacementBacktester(s)
        bt.run()
        res = bt.metrics()
        summary.append(res)
        all_trades.extend(bt.trades)

    mt5.shutdown()

    sdf = pd.DataFrame(summary)
    print("\n================ PERFORMANCE SUMMARY ================")
    print(sdf.to_string(index=False))
    print("=====================================================\n")

    if all_trades:
        pd.DataFrame(all_trades).to_csv(OUTPUT_REPORT, index=False)
        print(f"[+] Verified trade ledger saved to: {OUTPUT_REPORT}")

if __name__ == "__main__":
    run_suite()