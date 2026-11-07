import sys
sys.path.append(r"C:\Quant-Nexus-Eng")
import MetaTrader5 as mt5
import pandas as pd
from quantum_delta_daemon import MT5_PATH, SYMBOLS, InstitutionalKillzoneEngine, SmartMoneyStructureEngine

if mt5.initialize(path=MT5_PATH):
    print("\n=== ORB KILLZONE & SMC CONFLUENCE AUDIT ===")
    for sym in SYMBOLS:
        kz = InstitutionalKillzoneEngine.get_session_context(sym)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 30)
        session_name = kz.get("session", "UNKNOWN")
        if rates is None or len(rates) < 15:
            print(f"• {sym:<10} | Feed: OFFLINE / WEEKEND CLOSED | KZ: {session_name}")
            continue
        df = pd.DataFrame(rates)
        fvg = SmartMoneyStructureEngine.audit_fvg(df)
        mss = SmartMoneyStructureEngine.audit_mss(df)
        orb = InstitutionalKillzoneEngine.audit_orb_levels(df)
        
        breakout = orb.get("breakout", "NONE")
        fvg_type = fvg.get("type", "BALANCED")
        mss_shift = mss.get("shift", "NONE")
        print(f"• {sym:<10} | KZ: {session_name:<20} | ORB: {breakout:<24} | FVG: {fvg_type:<12} | MSS: {mss_shift}")
    print("===========================================\n")
    mt5.shutdown()
else:
    print("[-] MT5 initialization failed.")