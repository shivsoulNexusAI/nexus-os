import MetaTrader5 as mt5
from nexus_multi_straddle_daemon import DualGatedDynamicEngine, SYMBOLS

engine = DualGatedDynamicEngine()
engine.load_model()

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False):
    print("=" * 85)
    print("SILO 2 ASSET SCANNER: ML PROBABILITY & BRACKET GEOMETRY")
    print("=" * 85)
    
    for sym in SYMBOLS:
        tick = mt5.symbol_info_tick(sym)
        info = mt5.symbol_info(sym)
        if not tick or not info:
            continue
            
        spread_pts = (tick.ask - tick.bid) / info.point
        spread_ok, p90 = engine.check_spread_elasticity(sym, spread_pts)
        X, cur_atr, cur_price = engine.get_features(sym)
        
        p_exp = 1.0
        thresh = 0.75
        if engine.model_bundle and X is not None:
            clf = engine.model_bundle["model"]
            thresh = engine.model_bundle.get("decision_threshold", 0.75)
            p_exp = clf.predict_proba(X)[0, 1]
            
        status = "ELIGIBLE TO ARM" if (p_exp >= thresh and spread_ok) else "WAITING FILTER"
        print(f"{sym:<7} | Spot: {cur_price:10.3f} | Spread: {spread_pts:4.1f}pt | ATR: {cur_atr:8.3f} | ML P: {p_exp:.3f} (Req: >={thresh:.2f}) | {status}")

    mt5.shutdown()
    print("=" * 85)
else:
    print("[-] Terminal init failed.")