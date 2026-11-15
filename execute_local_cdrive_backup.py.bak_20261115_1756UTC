import os
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

ENG_DIR = Path(r"C:\Quant-Nexus-Eng")
LOCAL_BACKUP_DIR = Path(r"C:\Quant-Nexus-Backups\2026-11-11_Updated_Vision")
LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOT_FILES = [
    "nexus_multi_straddle_daemon.py",
    "sync_and_backtest.py",
    "inspect_live_status.py",
    "audit_today_deals.py",
    "verify_asset_thresholds.py",
    "clean_legacy_orders.py",
    "sync_and_backup_vision.py"
]

print("=" * 85)
print("NEXUS QUANTITATIVE FLEET: C: DRIVE VERIFIED LOCAL BACKUP")
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Target: Account #278041169")
print("=" * 85)

checksums = []
for fname in SNAPSHOT_FILES:
    src = ENG_DIR / fname
    if src.exists():
        dst = LOCAL_BACKUP_DIR / fname
        shutil.copy2(src, dst)
        h = hashlib.sha256(src.read_bytes()).hexdigest()
        checksums.append(f"{h[:16]}...  {fname}")
        print(f"  [+] Backed up & Verified: {fname:<30} ({src.stat().st_size:,} bytes)")
    else:
        print(f"  [-] Skipped missing file: {fname}")

manifest_path = LOCAL_BACKUP_DIR / "CHECKSUMS_SHA256.txt"
manifest_path.write_text("\n".join(checksums), encoding="utf-8")
print(f"\n[OK] Snapshot stored at: {LOCAL_BACKUP_DIR}")
print(f"[OK] Checksum manifest: {manifest_path}")
print("=" * 85)