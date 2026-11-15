import sqlite3
from pathlib import Path

for db_file in sorted(Path(r"C:\Quant-Nexus-Eng").glob("*.db")):
    print(f"--- DB: {db_file.name} ({db_file.stat().st_size} bytes) ---")
    try:
        conn = sqlite3.connect(str(db_file))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print("Tables:", tables)
        for t in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})").fetchall()]
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {cnt} rows | cols={cols}")
            if cnt > 0:
                last_row = conn.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 1").fetchone()
                print(f"    latest={last_row}")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")