import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SRC_DB = Path(r"C:\Quant-Nexus-Eng\nexus_ledger.db")
BACKUP_DIR = Path(r"C:\Quant-Nexus-Eng\db_backups")
RETENTION_DAYS = 14

def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not SRC_DB.exists():
        raise FileNotFoundError(f"Source database missing: {SRC_DB}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%MUTC")
    dst_db = BACKUP_DIR / f"nexus_ledger_{ts}.db"

    with sqlite3.connect(f"file:{SRC_DB}?mode=ro", uri=True, timeout=15.0) as src:
        with sqlite3.connect(str(dst_db)) as dst:
            src.backup(dst)

    # Prune backups older than RETENTION_DAYS
    cutoff = datetime.now(timezone.utc).timestamp() - (RETENTION_DAYS * 86400)
    for old_file in BACKUP_DIR.glob("nexus_ledger_*.db"):
        if old_file.stat().st_mtime < cutoff:
            old_file.unlink(missing_ok=True)

    print(f"[OK] Atomic SQLite backup created: {dst_db} ({dst_db.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
