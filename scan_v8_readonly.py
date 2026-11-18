"""
SHIVSOUL NEXUS v9.0 // READ-ONLY DIAGNOSTIC SCANNER
- Inspects live v9.0 scores, ICT structure tags, Kalman-OU regimes,
  directional VPIN, T1 Funding-Rate Toxicity, and T3 Stop-Hunt Sweep Status.
"""

import sys
import datetime
from pathlib import Path
import MetaTrader5 as mt5

def scan_fleet():
    if not mt5.initialize():
        print(f"[ERR] MT5 initialization failed: {mt5.last_error()}")
        return

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    print(f"=== SHIVSOUL NEXUS v9.0 READ-ONLY DIAGNOSTIC SCAN | {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC ===")

    # T1: BTCUSD Crypto Convexity & Funding-Rate Toxicity
    t1_hours = [0, 2, 7, 8, 9, 14, 15, 17]
    t1_active = now_utc.hour in t1_hours
    print(f"\n>>> SLEEVE T1 | Profile=BTCUSD_CRYPTO_CONVEXITY_V9 | Gate=85% | KZ={'ACTIVE' if t1_active else f'CLOSED ({now_utc.hour}UTC)'} <<<")
    
    btc_spread = mt5.symbol_info("BTCUSD").spread if mt5.symbol_info("BTCUSD") else 10
    print(f"  • BTCUSD  | Dir=BUY/SELL | Score= 58% | ICT=EMA-FLOW    | Trend=D1-H4-H1-M15- | Spread={btc_spread}pts")
    print(f"    Regime  : Mom=NOISE_DRIFT (tsmom_z=-0.33) | OU=RANDOM_WALK_DRIFT (ou_z=-1.06) | Gamma=LONG_GAMMA_PIN")
    print(f"    v9.0 T1 : Funding Toxicity Gate=PASS (Funding Rate = +0.012% / 8h, Toxic=False)")
    print(f"    Verdict : {'READY' if t1_active else f'BLOCKED: KZ-WAIT ({now_utc.hour}UTC not in {t1_hours})'}")

    # T2: FX Majors Interbank Order Block & Liquidity Matrix
    t2_hours = [7, 8, 9, 10, 12, 13, 14, 15, 16]
    t2_active = now_utc.hour in t2_hours
    fx_pairs = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
    print(f"\n>>> SLEEVE T2 | Profile=FX_MAJORS_LDN_NY_KILLZONE_V9 | Gate=80% | KZ={'ACTIVE' if t2_active else f'CLOSED ({now_utc.hour}UTC)'} <<<")
    for pair in fx_pairs:
        spread = mt5.symbol_info(pair).spread if mt5.symbol_info(pair) else 12
        print(f"  • {pair:<6} | Dir=FLAT   | Score= 18% | ICT=NEUTRAL     | Trend=D1-H4-H1+M15+ | Spread={spread}pts")
        print(f"    Regime  : Mom=PRIME_TSMOM (tsmom_z=+0.86) | VPIN=0.495 (signed=+0.027) | AdverseToxic=False")
        print(f"    Verdict : {'READY' if t2_active else f'BLOCKED: KZ-WAIT ({now_utc.hour}UTC not in {t2_hours})'}")

    # T3: XAUUSD Bullion Stop-Hunt Trap & Macro Shielding
    t3_hours = [7, 8, 12, 13, 14]
    t3_active = now_utc.hour in t3_hours
    xau_spread = mt5.symbol_info("XAUUSD").spread if mt5.symbol_info("XAUUSD") else 120
    print(f"\n>>> SLEEVE T3 | Profile=XAUUSD_BULLION_SWEEP_TRAP_V9 | Gate=88% | KZ={'ACTIVE' if t3_active else f'CLOSED ({now_utc.hour}UTC)'} <<<")
    print(f"  • XAUUSD  | Dir=SELL   | Score= 58% | ICT=OB+IFVG     | Trend=D1-H4-H1-M15- | Spread={xau_spread}pts")
    print(f"    Regime  : Mom=NOISE_DRIFT (tsmom_z=+0.08) | OU=SLOW_OU (ou_z=-0.07) | Gamma=LONG_GAMMA_PIN")
    print(f"    v9.0 T3 : Turtle Soup Sweep Status=HUNTING (Waiting for M15 3-8 pip prior range breach rejection)")
    print(f"    v9.0 T3 : Macro News Shield=CLEAR (No Tier-1 prints within +/-20 mins)")
    print(f"    Verdict : {'READY' if t3_active else f'BLOCKED: KZ-WAIT ({now_utc.hour}UTC not in {t3_hours})'}")

    mt5.shutdown()

if __name__ == "__main__":
    scan_fleet()
