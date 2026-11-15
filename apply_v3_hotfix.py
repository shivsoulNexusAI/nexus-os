from pathlib import Path

target = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")
code = target.read_text(encoding="utf-8")

# 1. Fix load_model() to use joblib.load first + import sklearn HistGradientBoostingClassifier
old_load = """    def load_model(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model_bundle = pickle.load(f)
            logging.info(f"[ML ENGINE LOADED] Regime model ready (AUC: {self.model_bundle.get('auc', 0.5):.4f})")
        except Exception as e:
            logging.warning(f"Could not load ML model: {e}. Defaulting to heuristic ATR gating.")
            self.model_bundle = None"""

new_load = """    def load_model(self):
        try:
            import joblib
            from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: F401
            self.model_bundle = joblib.load(MODEL_PATH)
            logging.info(f"[ML ENGINE LOADED] Regime model ready via joblib (AUC: {self.model_bundle.get('auc', 0.5):.4f})")
        except Exception as e:
            logging.warning(f"ML model load fallback ({e}). Enforcing strict ATR expansion ratio >= 1.15.")
            self.model_bundle = None"""

assert old_load in code, "load_model block not found"
code = code.replace(old_load, new_load, 1)

# 2. Enforce strict heuristic ATR expansion check when model_bundle is None (never blind 1.0)
old_pred = """                p_expansion = 1.0
                thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)
                if self.model_bundle:
                    clf = self.model_bundle["model"]
                    p_expansion = clf.predict_proba(X)[0, 1]"""

new_pred = """                thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)
                if self.model_bundle:
                    clf = self.model_bundle["model"]
                    p_expansion = clf.predict_proba(X)[0, 1]
                else:
                    exp_ratio = float(X["atr_expansion_ratio"].iloc[0]) if "atr_expansion_ratio" in X.columns else 1.0
                    p_expansion = min(0.95, max(0.0, (exp_ratio - 0.85) * 2.0))"""

assert old_pred in code, "prediction block not found"
code = code.replace(old_pred, new_pred, 1)

# 3. Respect actual deal exit timestamp in sync_whipsaw_history()
old_sync = """    def sync_whipsaw_history(self):
        \"\"\"Syncs recent closed exits into Nexus-OS AntiWhipsawEngine to quarantine choppy symbols.\"\"\"
        if not self.whipsaw:
            return
        now = datetime.now()
        deals = mt5.history_deals_get(now - timedelta(hours=4), now) or []
        for d in deals:
            if d.entry == 1 and d.ticket not in self.processed_deals:
                self.processed_deals.add(d.ticket)
                if d.symbol in SYMBOLS:
                    if d.profit < -0.10:
                        self.whipsaw.record_loss(d.symbol)
                    elif d.profit > 0.10:
                        self.whipsaw.record_win(d.symbol)"""

new_sync = """    def sync_whipsaw_history(self):
        \"\"\"Syncs recent closed exits using actual deal exit timestamps.\"\"\"
        if not self.whipsaw:
            return
        now = datetime.now()
        now_ts = int(time.time())
        deals = mt5.history_deals_get(now - timedelta(hours=2), now) or []
        for d in sorted(deals, key=lambda x: x.time):
            if d.entry == 1 and d.ticket not in self.processed_deals:
                self.processed_deals.add(d.ticket)
                if d.symbol in SYMBOLS and (now_ts - d.time) <= 3600:
                    if d.profit < -0.10:
                        self.whipsaw.record_loss(d.symbol)
                    elif d.profit > 0.10:
                        self.whipsaw.record_win(d.symbol)"""

assert old_sync in code, "sync_whipsaw_history block not found"
code = code.replace(old_sync, new_sync, 1)

target.write_text(code, encoding="utf-8")
print("[OK] Patched joblib ML loader, ATR fallback, and timestamp-aware AntiWhipsaw sync.")