import sqlite3
from pathlib import Path
from datetime import datetime

db_candidates = list(Path(r"C:\Quant-Nexus-Eng").glob("*.db")) + list(Path(r"C:\Quant-Nexus-Prod").glob("*.db"))

print("=" * 85)
print("INSPECTING HEARTBEATS & EXECUTION LEDGER")
print("=" * 85)

for db in db_candidates:
    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        if "heartbeats" in tables or any("heart" in t or "ledger" in t for t in tables):
            print(f"\nDatabase: {db.name} | Tables: {tables}")
            for t in tables:
                if "heart" in t:
                    cursor.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 5")
                    rows = cursor.fetchall()
                    print(f"  Recent entries in {t}: {rows}")
        conn.close()
    except Exception as e:
        pass
print("=" * 85)