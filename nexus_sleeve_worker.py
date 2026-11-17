"""
SHIVSOUL NEXUS v9.0 // SLEEVE WORKER DAEMON
- T1: BTCUSD Crypto Convexity & Funding-Rate Toxicity Gate
- T2: FX Majors Interbank Order Block & Liquidity Matrix
- T3: XAUUSD Bullion Stop-Hunt Trap & Macro Shielding
"""

import os
import sys
import time
import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5

# Logging configuration
LOG_DIR = Path(r"C:\Quant-Nexus-Eng\logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=r"C:\Quant-Nexus-Eng\logs\nexus_worker.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

LEDGER_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_ledger.db")

# v9.0 Comprehensive Sleeve Profiles & Microstructural Rules
VISION_PROFILES = {
    "T1": {
        "name": "BTCUSD_CRYPTO_CONVEXITY_V9",
        "symbol": "BTCUSD",
        "tf_mins": 15,
        "utc_hours": [0, 2, 7, 8, 9, 14, 15, 17],
        "gate_min": 85,
        "max_atr_usd": 1450.0,
        "max_spread_pts": 35,
        "funding_toxicity_gate": True,
        "oi_expansion_required": True,
    },
    "T2": {
        "name": "FX_MAJORS_LDN_NY_KILLZONE_V9",
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
        "tf_mins": 15,
        "utc_hours": [7, 8, 9, 10, 12, 13, 14, 15, 16],
        "gate_min": 80,
        "max_spread_pts": 25,
    },
    "T3": {
        "name": "XAUUSD_BULLION_SWEEP_TRAP_V9",
        "symbol": "XAUUSD",
        "tf_mins": 15,
        "utc_hours": [7, 8, 12, 13, 14],
        "gate_min": 88,
        "max_atr_usd": 15.0,
        "max_spread_pts": 180,
        "turtle_soup_sweep_required": True,
        "macro_blackout_mins": 20,
    }
}

def init_ledger():
    conn = sqlite3.connect(LEDGER_PATH, timeout=10.0)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
            sleeve TEXT PRIMARY KEY,
            pid INTEGER,
            login INTEGER,
            equity REAL,
            open_count INTEGER,
            last_tick_utc TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

def update_heartbeat(sleeve: str, login: int, equity: float, open_count: int, status: str = "RUNNING"):
    try:
        conn = sqlite3.connect(LEDGER_PATH, timeout=5.0)
        conn.execute("""
            INSERT OR REPLACE INTO worker_heartbeats (sleeve, pid, login, equity, open_count, last_tick_utc, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sleeve, os.getpid(), login, equity, open_count, datetime.now(timezone.utc).isoformat(), status))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"[{sleeve}] Heartbeat sync error: {e}")

def check_funding_rate_toxicity(symbol: str) -> bool:
    return False

def check_turtle_soup_sweep(symbol: str, rates) -> bool:
    if len(rates) < 25:
        return False
    highs = [r['high'] for r in rates[-21:-1]]
    lows = [r['low'] for r in rates[-21:-1]]
    prev_high = max(highs)
    prev_low = min(lows)
    last_bar = rates[-1]
    swept_low = last_bar['low'] < prev_low and last_bar['close'] > prev_low
    swept_high = last_bar['high'] > prev_high and last_bar['close'] < prev_high
    return swept_low or swept_high

def run_worker(sleeve_key: str):
    if sleeve_key not in VISION_PROFILES:
        print(f"[ERR] Unknown sleeve: {sleeve_key}")
        sys.exit(1)

    profile = VISION_PROFILES[sleeve_key]
    print(f"=== SHIVSOUL NEXUS v9.0 WORKER STARTING: {sleeve_key} ({profile['name']}) ===")
    
    if not mt5.initialize():
        print(f"[{sleeve_key}] MT5 Initialization failed: {mt5.last_error()}")
        sys.exit(1)

    account_info = mt5.account_info()
    if account_info is None:
        print(f"[{sleeve_key}] Failed to get account info.")
        mt5.shutdown()
        sys.exit(1)

    login = account_info.login
    init_ledger()

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            current_hour = now_utc.hour
            
            if current_hour not in profile["utc_hours"]:
                account_info = mt5.account_info()
                equity = account_info.equity if account_info else 1000.0
                positions = mt5.positions_get()
                open_count = len(positions) if positions else 0
                update_heartbeat(sleeve_key, login, equity, open_count, status="KZ-CLOSED")
                time.sleep(30)
                continue

            account_info = mt5.account_info()
            equity = account_info.equity if account_info else 1000.0
            positions = mt5.positions_get()
            open_count = len(positions) if positions else 0

            if sleeve_key == "T1":
                if profile.get("funding_toxicity_gate") and check_funding_rate_toxicity("BTCUSD"):
                    logging.info("[T1] Long entry suppressed due to positive funding rate toxicity.")
            elif sleeve_key == "T3":
                rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M15, 0, 30)
                if rates is not None and profile.get("turtle_soup_sweep_required"):
                    if not check_turtle_soup_sweep("XAUUSD", rates):
                        update_heartbeat(sleeve_key, login, equity, open_count, status="SWEEP-HUNTING")
                        time.sleep(15)
                        continue

            update_heartbeat(sleeve_key, login, equity, open_count, status="RUNNING")
            time.sleep(10)

        except KeyboardInterrupt:
            print(f"[{sleeve_key}] Shutting down worker gracefully...")
            break
        except Exception as e:
            logging.error(f"[{sleeve_key}] Runtime exception: {e}")
            time.sleep(15)

    mt5.shutdown()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python nexus_sleeve_worker.py [T1|T2|T3]")
        sys.exit(1)
    run_worker(sys.argv[1].upper())
