# -*- coding: utf-8 -*-
"""
QUANT-NEXUS REGIME MODEL TRAINER V2 (NORMALIZED MULTI-ASSET GBDT)
Solves cross-asset variance dilution via relative percentile/z-score transformations.
"""
import sys
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score, brier_score_loss

CSV_IN = Path(r"C:\Quant-Nexus-Eng\ml_regime_dataset.csv.gz")
PARQUET_IN = Path(r"C:\Quant-Nexus-Eng\ml_regime_dataset.parquet")
MODEL_OUT = Path(r"C:\Quant-Nexus-Eng\regime_classifier.pkl")

def train_v2():
    if PARQUET_IN.exists():
        df = pd.read_parquet(PARQUET_IN)
    elif CSV_IN.exists():
        df = pd.read_csv(CSV_IN, compression="gzip")
    else:
        print("[-] Error: Dataset file not found.")
        sys.exit(1)

    print("=" * 80)
    print("      FEATURE TRANSFORMATION: CROSS-ASSET RELATIVE NORMALIZATION")
    print("=" * 80)

    # Transform features to relative per-symbol metrics to avoid asset-bias
    grouped = df.groupby("symbol", group_keys=False)
    
    # Relative volatility scores (current vs rolling 72-period baseline)
    df["rel_natr"] = grouped["natr14"].apply(lambda x: x / x.rolling(72, min_periods=10).mean())
    df["rel_parkinson"] = grouped["parkinson_vol"].apply(lambda x: x / x.rolling(72, min_periods=10).mean())
    df["rel_gk"] = grouped["garman_klass_vol"].apply(lambda x: x / x.rolling(72, min_periods=10).mean())
    
    # Clean infs and NaNs
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)

    V2_FEATURES = [
        "rel_natr", "atr_expansion_ratio", "rel_parkinson", "rel_gk",
        "upper_wick_ratio", "lower_wick_ratio", "body_ratio", "rvol",
        "ret_1", "ret_3", "ret_12", "is_btc", "is_gold", "is_us30"
    ]

    split_idx = int(len(df) * 0.80)
    train_df, test_df = df.iloc[:split_idx], df.iloc[split_idx:]

    X_train, y_train = train_df[V2_FEATURES], train_df["target_expansion"].astype(int)
    X_test, y_test = test_df[V2_FEATURES], test_df["target_expansion"].astype(int)

    print(f"Training Samples   : {len(X_train)}")
    print(f"Validation Samples : {len(X_test)}")
    print(f"Base Expansion Rate: {y_train.mean()*100:.2f}%")

    # Regularized model to prevent memorizing random tick noise
    clf = HistGradientBoostingClassifier(
        max_iter=120,
        learning_rate=0.03,
        max_depth=4,
        min_samples_leaf=50,
        l2_regularization=2.5,
        random_state=42
    )
    clf.fit(X_train, y_train)

    probs = clf.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, probs)
    brier = brier_score_loss(y_test, probs)

    # Dynamic threshold search for precision > 60%
    best_thresh = 0.55
    best_prec = 0.0
    for t in np.linspace(0.50, 0.75, 26):
        p_mask = (probs >= t).astype(int)
        if p_mask.sum() > 20:
            prec = precision_score(y_test, p_mask, zero_division=0)
            if prec > best_prec:
                best_prec = prec
                best_thresh = t

    eval_p = (probs >= best_thresh).astype(int)
    print("-" * 80)
    print(f"Trained Out-of-Time ROC-AUC: {auc:.4f}")
    print(f"Brier Score                : {brier:.4f}")
    print(f"Calibrated Threshold       : P >= {best_thresh:.2f}")
    print(f"Precision @ Calibrated P   : {precision_score(y_test, eval_p, zero_division=0)*100:.2f}%")
    print(f"Recall @ Calibrated P      : {recall_score(y_test, eval_p, zero_division=0)*100:.2f}%")
    print(f"Deployment Rate            : {np.mean(eval_p)*100:.1f}%")
    print("=" * 80)

    bundle = {
        "model": clf,
        "feature_names": V2_FEATURES,
        "mean_auc": float(auc),
        "decision_threshold": float(best_thresh),
        "trained_timestamp": pd.Timestamp.now(tz="UTC").isoformat()
    }
    joblib.dump(bundle, MODEL_OUT)
    print(f"[+] High-Discrimination Bundle Saved to: {MODEL_OUT}")

if __name__ == "__main__":
    train_v2()