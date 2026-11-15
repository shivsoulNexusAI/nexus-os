# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_telemetry.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

T1_LOGIN = 278062038

# Check schema / inspect deal execution attributes
cur.execute("PRAGMA table_info(deals_history)")
columns = [col[1] for col in cur.fetchall()]

# Sample recent deals to check order IDs, comments, and magic numbers if stored
cur.execute("""
    SELECT ticket, order_id, symbol, type, volume, price_open, price_close, profit, net_pnl, time_close
    FROM deals_history
    WHERE login = ?
    ORDER BY time_close DESC
    LIMIT 10
""", (T1_LOGIN,))

rows = cur.fetchall()
print("=" * 85)
print("             TERMINAL 1 EXECUTION MECHANISM RECONNAISSANCE")
print("=" * 85)
for r in rows:
    ticket, order_id, sym, side, vol, p_open, p_close, prof, net, t_close = r
    print(f"Ticket: {ticket:<10} | Order: {order_id:<10} | {sym:<7} {side:<4} {vol:<4} | In: {p_open} -> Out: {p_close} | Net: ${net:+6.2f} | {t_close}")

print("=" * 85)
conn.close()