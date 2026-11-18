# =====================================================================
# SHIVSOUL NEXUS v7.0 // DEEP ALPHA & EXECUTION DELTA DIAGNOSTIC
# =====================================================================
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
import MetaTrader5 as mt5
from nexus_ship_core import SLEEVES

DB_PATH = Path("nexus_ledger.db")

def inspect_ledger_history():
    print("=== 1. SQLITE ORDER INTENTS & VETO FORENSICS ===")
    if not DB_PATH.exists():
        print("[ERR] nexus_ledger.db not found.")
        return
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r["name"] for r in cur.fetchall()]
    print(f"Tables in DB: {tables}\n")

    if "order_intents" in tables:
        cur.execute("SELECT * FROM order_intents ORDER BY created_utc DESC LIMIT 25;")
        rows = cur.fetchall()
        print(f"Total recent order_intents ({len(rows)}):")
        for r in rows:
            print(" ", dict(r))

    conn.close()

def inspect_mt5_deals_since_monday():
    print("\n=== 2. MT5 REALIZED DEAL HISTORY (LAST 4 DAYS) ===")
    start_dt = datetime.now(timezone.utc) - timedelta(days=4)
    end_dt = datetime.now(timezone.utc) + timedelta(hours=2)

    for sleeve, cfg in SLEEVES.items():
        print(f"\n>>> SLEEVE {sleeve} (#{cfg['login']}) <<<")
        if not mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"]):
            print(f"  [ERR] MT5 init failed: {mt5.last_error()}")
            continue
        try:
            deals = mt5.history_deals_get(start_dt, end_dt)
            if not deals:
                print("  No deals found.")
                continue
            net_pnl = 0.0
            for d in deals:
                if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT):
                    pnl = d.profit + d.swap + d.commission
                    net_pnl += pnl
                    t_str = datetime.fromtimestamp(d.time, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    print(f"  [CLOSE] {t_str} | {d.symbol} | Vol={d.volume} | Price={d.price} | NetPnL=${pnl:+.2f} | Comment='{d.comment}'")
                elif d.entry == mt5.DEAL_ENTRY_IN:
                    t_str = datetime.fromtimestamp(d.time, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    side = "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL"
                    print(f"  [OPEN ] {t_str} | {d.symbol} {side} | Vol={d.volume} | Price={d.price} | Comment='{d.comment}'")
            print(f"  --> Realized Net PnL: ${net_pnl:+.2f}")
        finally:
            mt5.shutdown()

if __name__ == "__main__":
    inspect_ledger_history()
    inspect_mt5_deals_since_monday()
