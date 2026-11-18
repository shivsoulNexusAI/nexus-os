import os
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
import joblib

def build_and_serialize_model():
    print("[*] Generating synthetic historical feature matrix for training...")
    # Simulated feature set: [ATR_Ratio, Volume_Delta, Spread_Ratio, Momentum_Score, Volatility_Index]
    np.random.seed(42)
    X_train = np.random.randn(1000, 5)
    # Target: 0 = Mean-Reverting, 1 = Trending
    y_train = np.random.choice([0, 1], size=1000, p=[0.55, 0.45])

    print("[*] Constructing hardened scikit-learn Pipeline...")
    pipeline = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('classifier', HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.05,
            random_state=42
        ))
    ])

    print("[*] Fitting model pipeline...")
    pipeline.fit(X_train, y_train)

    bundle_path = "model_bundle_v2.joblib"
    joblib.dump(pipeline, bundle_path)
    print(f"[SUCCESS] Model bundle successfully serialized to: {os.path.abspath(bundle_path)}")

if __name__ == "__main__":
    build_and_serialize_model()
