# -*- coding: utf-8 -*-
"""
QuantNexus Mission Delta: Local SQLite Telemetry Engine
Captures trade execution records, slippage, and cadence metrics into nexus_telemetry.db.
"""
import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import MetaTrader5 as mt5

DB_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_telemetry.db")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\telemetry_db.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("TelemetryDB")

FLEET = [
    {"login": 278062038, "path": r"C:\MT5_Quant_278061453\terminal64.exe", "tag": "T1"},
    {"login": 278062039, "path": r"C:\MT5_Pending_278041169\terminal64.exe", "tag": "T2"},
    {"login": 278062042, "path": r"C:\MT5_HFT_278041671\terminal64.exe", "tag": "T3"}
]

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS deals_history (
            ticket INTEGER PRIMARY KEY,
            order_id INTEGER,
            login INTEGER,
            symbol TEXT,
            type TEXT,
            volume REAL,
            price_open REAL,
            price_close REAL,
            profit REAL,
            commission REAL,
            swap REAL,
            net_pnl REAL,
            time_close TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS fleet_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            total_balance REAL,
            total_equity REAL,
            floating_pnl REAL,
            t1_equity REAL,
            t2_equity REAL,
            t3_equity REAL
        )
    ''')

    conn.commit()
    conn.close()
    log.info("Initialized SQLite database schema at %s", DB_PATH)

def sync_deals():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    from_date = datetime.now(timezone.utc) - timedelta(days=7)
    to_date = datetime.now(timezone.utc)

    total_synced = 0

    for term in FLEET:
        if not mt5.initialize(path=term["path"]):
            continue
        
        deals = mt5.history_deals_get(from_date, to_date)
        mt5.shutdown()

        if not deals:
            continue

        for d in deals:
            if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT) and d.profit != 0:
                side = "BUY" if d.type == mt5.ORDER_TYPE_BUY else "SELL"
                net = d.profit + d.commission + d.swap
                close_dt = datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat()

                cur.execute('''
                    INSERT OR IGNORE INTO deals_history (
                        ticket, order_id, login, symbol, type, volume,
                        price_open, price_close, profit, commission, swap, net_pnl, time_close
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    d.ticket, d.order, term["login"], d.symbol, side, d.volume,
                    0.0, d.price, round(d.profit, 2), round(d.commission, 2),
                    round(d.swap, 2), round(net, 2), close_dt
                ))
                if cur.rowcount > 0:
                    total_synced += 1

    conn.commit()
    conn.close()
    if total_synced > 0:
        log.info("Synced %d new trade records to database.", total_synced)

def capture_snapshot():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    equities = {}
    balances = {}

    for term in FLEET:
        if mt5.initialize(path=term["path"]):
            acc = mt5.account_info()
            if acc:
                equities[term["tag"]] = acc.equity
                balances[term["tag"]] = acc.balance
            mt5.shutdown()

    if len(equities) == 3:
        total_bal = sum(balances.values())
        total_eq = sum(equities.values())
        float_pnl = total_eq - total_bal
        now_iso = datetime.now(timezone.utc).isoformat()

        cur.execute('''
            INSERT INTO fleet_snapshots (
                timestamp, total_balance, total_equity, floating_pnl,
                t1_equity, t2_equity, t3_equity
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            now_iso, round(total_bal, 2), round(total_eq, 2), round(float_pnl, 2),
            round(equities["T1"], 2), round(equities["T2"], 2), round(equities["T3"], 2)
        ))
        conn.commit()
    conn.close()

def run_loop():
    init_database()
    log.info("Starting Telemetry Database sync loop...")
    while True:
        try:
            sync_deals()
            capture_snapshot()
        except Exception as e:
            log.error("Telemetry sync exception: %s", e)
        time.sleep(300) # Syncs every 5 minutes

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--audit":
        init_database()
        sync_deals()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(net_pnl) FROM deals_history")
        row = cur.fetchone()
        print("=" * 60)
        print(f"[*] NEXUS TELEMETRY DB AUDIT:")
        print(f"    • Total Recorded Deals: {row[0]}")
        print(f"    • Cumulative Recorded Net: ${row[1]:+,.2f}" if row[1] else "    • Cumulative Recorded Net: $0.00")
        print("=" * 60)
        conn.close()
    else:
        run_loop()