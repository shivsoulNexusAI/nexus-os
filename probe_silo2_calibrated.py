import MetaTrader5 as mt5
from nexus_multi_straddle_daemon import DualGatedDynamicEngine, SYMBOLS

engine = DualGatedDynamicEngine()
engine.load_model()

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False):
    print("=" * 85)
    print("ACCOUNT #278062039: LIVE ASSET ARMED STATUS (CALIBRATED THRESHOLD: 0.65)")
    print("=" * 85)
    
    thresh = engine.model_bundle.get("decision_threshold", 0.65) if engine.model_bundle else 0.65
    
    for sym in SYMBOLS:
        tick = mt5.symbol_info_tick(sym)
        info = mt5.symbol_info(sym)
        if not tick or not info:
            continue
            
        spread_pts = (tick.ask - tick.bid) / info.point
        spread_ok, p90 = engine.check_spread_elasticity(sym, spread_pts)
        pos_cnt, ord_cnt = engine.check_active_exposure(sym)
        X, cur_atr, cur_price = engine.get_features(sym)
        
        clf = engine.model_bundle["model"] if engine.model_bundle else None
        p_exp = clf.predict_proba(X)[0, 1] if (clf and X is not None) else 0.0
        
        can_arm = (p_exp >= thresh) and spread_ok and (pos_cnt == 0 and ord_cnt < 2)
        status = ">>> ELIGIBLE & ARMED <<<" if can_arm else f"FILTER HOLD (Spread:{spread_ok}, Pos:{pos_cnt}, Ord:{ord_cnt})"
        
        print(f"{sym:<7} | ML P: {p_exp:.3f} (Req: >={thresh:.2f}) | Spread: {spread_pts:4.1f}pt (P90: {p90:.1f}pt) | {status}")

    orders = mt5.orders_get() or []
    positions = mt5.positions_get() or []
    print("-" * 85)
    print(f"TERMINAL STATUS: Positions: {len(positions)} | Working Orders: {len(orders)}")
    for o in orders:
        ot = "BUY_STOP" if o.type == 4 else ("SELL_STOP" if o.type == 5 else str(o.type))
        print(f"  -> ORD #{o.ticket} | {o.symbol:<7} {ot} {o.volume_current:.2f}L @ {o.price_open:.5f} | SL: {o.sl:.5f} | TP: {o.tp:.5f} | Tag: {o.comment}")
    mt5.shutdown()
    print("=" * 85)
else:
    print("[-] MT5 Init failed.")