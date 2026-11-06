# -*- coding: utf-8 -*-
import os
import joblib
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import warnings

# Suppress sklearn feature validation noise
warnings.filterwarnings("ignore", category=UserWarning)

MODEL_PATH = "regime_model.joblib"

class RegimeGovernor:
    def __init__(self):
        self.model_data = None
        if os.path.exists(MODEL_PATH):
            try:
                self.model_data = joblib.load(MODEL_PATH)
            except Exception as e:
                print(f"[-] Error loading regime model: {e}")

    def evaluate(self, symbol: str):
        default_resp = {
            "symbol": symbol,
            "regime": "RANGE_ACCUMULATION",
            "verdict": "APPROVED_STANDARD",
            "confidence": 1.0,
            "risk_multiplier": 0.75,
            "efficiency": 0.5,
            "atr_ratio": 1.0,
            "reason": ""
        }

        if not self.model_data:
            default_resp["reason"] = "Model weights file not found"
            return default_resp

        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 80)
        if rates is None or len(rates) < 75:
            default_resp["reason"] = f"Insufficient M5 bars (got {0 if rates is None else len(rates)})"
            return default_resp

        df = pd.DataFrame(rates)

        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["close"].shift(1)),
                abs(df["low"] - df["close"].shift(1))
            )
        )
        atr_fast = tr.rolling(14).mean().iloc[-1]
        atr_slow = tr.rolling(70).mean().iloc[-1]
        atr_ratio = atr_fast / (atr_slow + 1e-9)

        net_change = abs(df["close"].iloc[-1] - df["close"].iloc[-16])
        total_path = tr.iloc[-15:].sum()
        efficiency = net_change / (total_path + 1e-9)

        log_ret = np.log(df["close"].iloc[-1] / (df["close"].iloc[-2] + 1e-9))
        vol_15 = np.log(df["close"] / df["close"].shift(1)).iloc[-15:].std()
        if np.isnan(vol_15):
            vol_15 = 0.0001

        c_range = df["high"].iloc[-1] - df["low"].iloc[-1]
        c_body = abs(df["close"].iloc[-1] - df["open"].iloc[-1])
        wick_ratio = (c_range - c_body) / (c_range + 1e-9)

        feature_names = self.model_data.get("feature_names", ["log_ret", "vol_15", "atr_ratio", "efficiency", "wick_ratio"])
        feat_df = pd.DataFrame([[log_ret, vol_15, atr_ratio, efficiency, wick_ratio]], columns=feature_names)

        try:
            scaler = self.model_data["scaler"]
            gmm = self.model_data["model"]
            labels = self.model_data["cluster_labels"]

            X_scaled = scaler.transform(feat_df)
            probs = gmm.predict_proba(X_scaled)[0]
            cluster = int(np.argmax(probs))
            confidence = float(probs[cluster])
            regime = labels.get(cluster, "RANGE_ACCUMULATION")

            if regime == "CHOP_VETO":
                verdict = "VETO"
                risk_mult = 0.0
            elif regime == "CLEAN_TREND":
                verdict = "APPROVED_AGGRESSIVE"
                risk_mult = 1.0
            else:
                verdict = "APPROVED_STANDARD"
                risk_mult = 0.75

            return {
                "symbol": symbol,
                "regime": regime,
                "verdict": verdict,
                "confidence": confidence,
                "risk_multiplier": risk_mult,
                "efficiency": round(efficiency, 3),
                "atr_ratio": round(atr_ratio, 2),
                "reason": "OK"
            }
        except Exception as e:
            default_resp["reason"] = f"Inference exception: {e}"
            return default_resp

if __name__ == "__main__":
    if mt5.initialize():
        gov = RegimeGovernor()
        for sym in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]:
            res = gov.evaluate(sym)
            mult = res.get('risk_multiplier', 1.0)
            print(f"[{sym}] Regime: {res['regime']} | Verdict: {res['verdict']} ({res['confidence']*100:.1f}%) | Multiplier: {mult}x | Note: {res.get('reason','')}")
        mt5.shutdown()
    else:
        print("[-] MetaTrader 5 initialization failed.")
