import MetaTrader5 as mt5
from mss_matrix import (
    analyze_higher_timeframe_context,
    audit_htf_order_block,
    detect_institutional_liquidity_grab,
    audit_rejection_order_block,
    audit_fvg_imbalance,
    audit_breaker_block,
    audit_liquidity_void
)

if mt5.initialize():
    symbols = ['USDJPY', 'BTCUSD', 'EURUSD', 'XAUUSD', 'GBPUSD']
    print("=" * 85)
    print("🏛️ [COMPLETE 7-TIER ICT PD ARRAY LIVE AUDIT]")
    print("=" * 85)
    for s in symbols:
        h1 = audit_htf_order_block(s)
        htf = analyze_higher_timeframe_context(s)
        liq = detect_institutional_liquidity_grab(s, htf.get('h4_bias', 'NEUTRAL'))
        ob = audit_rejection_order_block(s)
        fvg = audit_fvg_imbalance(s)
        bb = audit_breaker_block(s)
        void = audit_liquidity_void(s)

        print(f"\nAsset: {s:<7} | Spot: {h1.get('cur_price', 0.0)} | Dealing Range: {h1.get('h1_bias', 'N/A')}")
        print(f"  • Tier 7 (Old High/Low Sweep) : {liq.get('type', 'NONE')} - {liq.get('desc', 'None')}")
        print(f"  • Tier 6 (Rejection Block)    : {'DETECTED' if ob.get('ob_price', 0) > 0 else 'NONE'} ({ob.get('ob_price', 0.0)})")
        print(f"  • Tier 5 (Order Block)        : {h1.get('ob_state', 'NONE')}")
        print(f"  • Tier 4 (Fair Value Gap)     : {fvg.get('fvg_type', 'NONE')} [{fvg.get('fvg_bottom', 0.0)} - {fvg.get('fvg_top', 0.0)}]")
        print(f"  • Tier 3 (Liquidity Void)     : {void.get('type', 'NONE')}")
        print(f"  • Tier 2 (Breaker Block)      : {bb.get('type', 'NONE')}")
    print("=" * 85)
    mt5.shutdown()
