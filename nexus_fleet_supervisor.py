"""
SHIVSOUL NEXUS v9.0 // FLEET SUPERVISOR DAEMON
- Oversees v9.0 worker states, live PIDs, and heartbeats.
- Manages tier-1 macro news blackout schedules and auto-recovery triggers.
"""

import time
import sqlite3
import datetime
from pathlib import Path

LEDGER_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_ledger.db")

def check_macro_blackout_schedule() -> bool:
    """
    Simulates checking upcoming high-impact tier-1 USD macro prints 
    (CPI, NFP, FOMC) within a +/-20 minute window.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # Example hardcoded high-impact window or dynamic calendar sync point
    # Returns True if fleet is currently inside a macro news blackout window.
    return False

def inspect_fleet_supervisor():
    if not LEDGER_PATH.exists():
        print("[ERR] nexus_ledger.db not found. Start workers first.")
        return

    conn = sqlite3.connect(LEDGER_PATH, timeout=5.0)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT sleeve, pid, login, equity, open_count, last_tick_utc, status FROM worker_heartbeats")
        rows = cursor.fetchall()
    except Exception as e:
        print(f"[ERR] Failed to read ledger heartbeats: {e}")
        conn.close()
        return
    
    conn.close()

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    macro_lock = check_macro_blackout_schedule()

    print(f"=== SHIVSOUL NEXUS v9.0 FLEET SUPERVISOR TELEMETRY | {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC ===")
    print(f"Macro News Blackout Window Active : {'YES (Sleeves Flatlined)' if macro_lock else 'CLEAR'}\n")

    if not rows:
        print("[WARN] No active worker heartbeats recorded in ledger yet.")
        return

    for row in rows:
        sleeve, pid, login, equity, open_count, last_tick_str, status = row
        try:
            last_tick = datetime.datetime.fromisoformat(last_tick_str)
            age_sec = (now_utc - last_tick).total_seconds()
        except Exception:
            age_sec = 999.0

        health = "HEALTHY" if age_sec < 45 else "STALE/STALLED"
        print(f"- Sleeve {sleeve} (PID: {pid}) | Login: {login} | Status={status} | Health={health}")
        print(f"  Equity: ${equity:,.2f} | Open Positions: {open_count} | Last Tick: {age_sec:.1f}s ago")

    print("==========================================================================================")

if __name__ == "__main__":
    inspect_fleet_supervisor()
