import MetaTrader5 as mt5
from nexus_multi_straddle_daemon import DualGatedDynamicEngine, SYMBOLS, ASSET_THRESHOLDS, DEFAULT_THRESHOLD

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
engine = DualGatedDynamicEngine()
engine.load_model()

if mt5.initialize(path=TERMINAL, portable=False):
    print("=" * 90)
    print("ASSET-SPECIFIC ML REGIME GATING AUDIT")
    print("=" * 90)
    for sym in SYMBOLS:
        req_thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)
        X, cur_atr, cur_price = engine.get_features(sym)
        clf = engine.model_bundle["model"] if engine.model_bundle else None
        p_val = clf.predict_proba(X)[0, 1] if (clf and X is not None) else 0.0
        
        status = ">>> ARMED <<<" if p_val >= req_thresh else "FILTERED (Below Hurdle)"
        print(f"{sym:<7} | ML P: {p_val:.3f} | Required: >={req_thresh:.2f} | Status: {status}")
    print("=" * 90)
    mt5.shutdown()
else:
    print("[-] MT5 Init failed.")