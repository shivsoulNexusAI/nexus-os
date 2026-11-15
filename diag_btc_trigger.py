import os
import json
import subprocess
from pathlib import Path
import MetaTrader5 as mt5

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
NEW_LOGIN = 278062038
NEW_SERVER = "Exness-MT5Trial5"
NEW_PASSWORD = r"H@ngkook3695"

# 1. Find all Python files still referencing old account 278062038
print("[*] Scanning C:\\Quant-Nexus-Eng for old account references (278062038)...")
for py_file in BASE_DIR.glob("*.py"):
    content = py_file.read_text(encoding="utf-8", errors="ignore")
    if "278062038" in content:
        updated = content.replace("278062038", str(NEW_LOGIN))
        py_file.write_text(updated, encoding="utf-8")
        print(f"  [UPDATED] Migrated {py_file.name} -> {NEW_LOGIN}")

# 2. Check running Python processes
print("\n[*] Active Python processes on VPS:")
out = subprocess.check_output('wmic process where "name=\'python.exe\'" get ProcessId,CommandLine', shell=True).decode(errors="ignore")
for line in out.strip().splitlines():
    if "python" in line.lower():
        print(" ", line.strip())

# 3. Inspect Exness BTCUSD Execution & Filling Mode Requirements on #278062038
print("\n[*] Auditing Exness BTCUSD Order Execution Specs on #278062038...")
if mt5.initialize() and mt5.login(NEW_LOGIN, password=NEW_PASSWORD, server=NEW_SERVER):
    mt5.symbol_select("BTCUSD", True)
    sym = mt5.symbol_info("BTCUSD")
    tick = mt5.symbol_info_tick("BTCUSD")
    if sym and tick:
        print(f"  Symbol: {sym.name} | Trade Mode: {sym.trade_mode} | Filling Flags: {sym.filling_mode}")
        print(f"  Min Lot: {sym.volume_min} | Step: {sym.volume_step} | Stops Level: {sym.trade_stops_level} pts")
        print(f"  Live Quote: Bid={tick.bid} | Ask={tick.ask} | Spread={(tick.ask - tick.bid)/sym.point:.0f} pts")
        
        # Run a zero-risk order_check() to confirm exact filling mode accepted by Exness
        for mode_name, mode_val in [("IOC", mt5.ORDER_FILLING_IOC), ("FOK", mt5.ORDER_FILLING_FOK), ("RETURN", mt5.ORDER_FILLING_RETURN)]:
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": "BTCUSD",
                "volume": sym.volume_min,
                "type": mt5.ORDER_TYPE_BUY,
                "price": tick.ask,
                "sl": round(tick.ask - 30000 * sym.point, sym.digits),
                "tp": round(tick.ask + 60000 * sym.point, sym.digits),
                "deviation": 30,
                "magic": NEW_LOGIN,
                "comment": "QuantNexus Check",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mode_val,
            }
            chk = mt5.order_check(req)
            print(f"  [ORDER_CHECK {mode_name}] Retcode: {chk.retcode if chk else 'None'} | Comment: {chk.comment if chk else 'None'}")
    mt5.shutdown()
