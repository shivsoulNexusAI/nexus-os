import MetaTrader5 as mt5
from m5_structural_trail import get_latest_m5_swing, BUFFER_FACTORS

if mt5.initialize():
    positions = mt5.positions_get() or []
    target_symbols = ["XAUUSD", "BTCUSD"]
    
    print("=" * 65)
    print("🎯 [M5 STRUCTURAL SWING & TRAILING CANDIDATES]")
    print("=" * 65)
    
    for sym in target_symbols:
        swings = get_latest_m5_swing(sym)
        buff = BUFFER_FACTORS.get(sym, 0.0)
        sym_positions = [p for p in positions if p.symbol == sym]
        
        print(f"\nAsset: {sym}")
        print(f"  • Confirmed M5 Swing High : {swings['swing_high']}")
        print(f"  • Confirmed M5 Swing Low  : {swings['swing_low']}")
        print(f"  • Protection Buffer       : ±{buff}")
        
        if sym_positions:
            for p in sym_positions:
                side = "BUY" if p.type == 0 else "SELL"
                if p.type == 0:
                    cand_sl = round(swings['swing_low'] - buff, 2 if "BTC" in sym else 3)
                    action = "CAN TIGHTEN" if (cand_sl > p.sl and cand_sl > p.price_open) else "HOLDING (Pending higher swing)"
                else:
                    cand_sl = round(swings['swing_high'] + buff, 2 if "BTC" in sym else 3)
                    action = "CAN TIGHTEN" if ((p.sl == 0.0 or cand_sl < p.sl) and cand_sl < p.price_open) else "HOLDING (Pending lower swing)"
                
                print(f"  • Position #{p.ticket} ({side} {p.volume}L):")
                print(f"      Open Price : {p.price_open}")
                print(f"      Current SL : {p.sl}")
                print(f"      Current Spot: {p.price_current}")
                print(f"      Target SL  : {cand_sl} -> Status: {action}")
        else:
            print(f"  • No active positions on {sym}.")
            
    print("\n" + "=" * 65)
    
    # Execute structural trail pass
    from m5_structural_trail import execute_structural_trailing
    trail_res = execute_structural_trailing(target_symbols)
    if trail_res:
        print("⚡ ACTIONS TAKEN:")
        for r in trail_res:
            print("  " + r)
    else:
        print("[+] Trailing pass: Stops are currently at optimal structure.")
        
    mt5.shutdown()
else:
    print("[-] MT5 failed to initialize.")
