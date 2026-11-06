# -*- coding: utf-8 -*-
import os
import joblib
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import RobustScaler

MODEL_SAVE_PATH = "regime_model.joblib"
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
TIMEFRAME = mt5.TIMEFRAME_M5
BARS_PER_SYMBOL = 15000

FEATURE_COLS = ["log_ret", "vol_15", "atr_ratio", "efficiency", "wick_ratio"]

def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    feats = pd.DataFrame(index=df.index)
    feats["log_ret"] = np.log(df["close"] / (df["close"].shift(1) + 1e-9))
    feats["vol_15"] = feats["log_ret"].rolling(15).std()
    
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1))
        )
    )
    atr_fast = tr.rolling(14).mean()
    atr_slow = tr.rolling(70).mean()
    feats["atr_ratio"] = atr_fast / (atr_slow + 1e-9)
    
    net_change = abs(df["close"] - df["close"].shift(15))
    total_path = tr.rolling(15).sum()
    feats["efficiency"] = net_change / (total_path + 1e-9)
    
    candle_range = df["high"] - df["low"]
    candle_body = abs(df["close"] - df["open"])
    feats["wick_ratio"] = (candle_range - candle_body) / (candle_range + 1e-9)
    
    return feats[FEATURE_COLS].dropna()

def pull_mt5_dataset():
    if not mt5.initialize():
        raise RuntimeError("MT5 initialization failed.")
        
    combined = []
    print("[*] Pulling historical M5 institutional bars from MT5...")
    
    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, BARS_PER_SYMBOL)
        if rates is None or len(rates) < 500:
            continue
        df = pd.DataFrame(rates)
        feats = extract_features(df)
        combined.append(feats)
        print(f"[+] Processed {len(feats)} feature vectors for {sym}")
        
    mt5.shutdown()
    return pd.concat(combined, axis=0).reset_index(drop=True)

def train_and_export():
    dataset = pull_mt5_dataset()
    print(f"\n[*] Total training matrix shape: {dataset.shape}")
    
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(dataset)
    
    print("[*] Fitting 3-Component Gaussian Mixture Model...")
    gmm = GaussianMixture(
        n_components=3,
        covariance_type="full",
        random_state=42,
        n_init=5
    )
    gmm.fit(X_scaled)
    
    means = scaler.inverse_transform(gmm.means_)
    atr_idx = FEATURE_COLS.index("atr_ratio")
    eff_idx = FEATURE_COLS.index("efficiency")
    
    # Sort clusters:
    # 1. Highest efficiency -> CLEAN_TREND
    # 2. Of remaining, highest ATR ratio -> CHOP_VETO
    # 3. Final cluster -> RANGE_ACCUMULATION
    clusters = list(range(3))
    eff_cluster = int(np.argmax(means[:, eff_idx]))
    clusters.remove(eff_cluster)
    
    chop_cluster = clusters[int(np.argmax(means[clusters, atr_idx]))]
    clusters.remove(chop_cluster)
    range_cluster = clusters[0]
    
    regime_labels = {
        eff_cluster: "CLEAN_TREND",
        chop_cluster: "CHOP_VETO",
        range_cluster: "RANGE_ACCUMULATION"
    }
    
    print("\n--- REGIME CLUSTERS LOCKED ---")
    for cid, label in regime_labels.items():
        print(f"Cluster {cid} -> [{label}]: ATR Ratio Mean={means[cid, atr_idx]:.2f}, Efficiency={means[cid, eff_idx]:.2f}")
        
    payload = {
        "scaler": scaler,
        "model": gmm,
        "feature_names": FEATURE_COLS,
        "cluster_labels": regime_labels
    }
    
    joblib.dump(payload, MODEL_SAVE_PATH)
    print(f"\n[SUCCESS] Model successfully serialized to '{MODEL_SAVE_PATH}'")

if __name__ == "__main__":
    train_and_export()
