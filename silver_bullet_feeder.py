"""
QuantNexus Live Feeder: Connects MT5 (Account 278017866) to Silver Bullet Engine.
Scans the 6-asset fleet across M15/M5 timeframes for institutional setups.
"""

import sys
import MetaTrader5 as mt5
from datetime import datetime, timezone
from silver_bullet_sniper import evaluate_silver_bullet, check_killzone, calculate_atr

FLEET_SYMBOLS = ["BTCUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY"]
MT5_PATH = r"C:\MT5_Quant_278017866\terminal64.exe"
ACCOUNT = 278017866

def init_mt5() -> bool:
    if mt5.initialize(path=MT5_PATH):
        login_info = mt5.account_info()
        if login_info and login_info.login == ACCOUNT:
            return True
        # If terminal open on different login, attempt direct login
        return mt5.login(ACCOUNT)
    return False

def scan_fleet():
    if not init_mt5():
        print("[-] Failed to initialize MT5 terminal on Account 278017866.")
        return

    in_kz, kz_name = check_killzone()
    print(f"[*] MT5 Connected | Account: {ACCOUNT}")
    print(f"[*] Killzone Status: {'ACTIVE (' + kz_name + ')' if in_kz else 'INACTIVE (Off-Hours)'}")
    print("=" * 65)

    detected_setups = []

    for sym in FLEET_SYMBOLS:
        tick = mt5.symbol_info_tick(sym)
        sym_info = mt5.symbol_info(sym)
        if tick is None or sym_info is None:
            print(f"[-] {sym:<7} | No tick data available.")
            continue

        point = sym_info.point
        spread_pts = (tick.ask - tick.bid)
        digits = sym_info.digits

        # Fetch last 30 bars on M5 (Standard Silver Bullet delivery timeframe)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 16:
            print(f"[-] {sym:<7} | Insufficient M5 bar history.")
            continue

        # Format into dictionary list for evaluation engine
        candles = [
            {
                "open": float(r['open']),
                "high": float(r['high']),
                "low": float(r['low']),
                "close": float(r['close']),
                "time": r['time']
            }
            for r in rates
        ]

        atr = calculate_atr(candles, period=14)
        setup = evaluate_silver_bullet(sym, candles, spread_pts=spread_pts, min_rr=2.0)

        if setup:
            detected_setups.append(setup)
            print(f"[!] *** SILVER BULLET DETECTED ***")
            print(f"    Asset: {setup.symbol} | Dir: {setup.direction} | KZ: {setup.killzone}")
            print(f"    Entry (50% MT): {setup.entry_price:,.{digits}f}")
            print(f"    SL: {setup.stop_loss:,.{digits}f} | TP: {setup.take_profit:,.{digits}f} (R:R {setup.risk_reward}:1)")
            print(f"    Displacement: {setup.displacement_ratio*100:.1f}% | ATR: {atr:.{digits}f}")
        else:
            print(f"[+] {sym:<7} | Spread: {spread_pts/point:.1f} pts | ATR(14): {atr:.{digits}f} | No FVG/KZ Confluence")

    print("=" * 65)
    print(f"[*] Fleet scan complete. Total qualified sniper triggers: {len(detected_setups)}")
    mt5.shutdown()

if __name__ == "__main__":
    scan_fleet()