"""
SHIVSOUL NEXUS // AUTOMATED JSON SNAPSHOT & RETENTION DAEMON
"""

import sys
import os
import json
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone

# Bulletproof root path resolution
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.trade_logger import NexusTradeLogger
from core.telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (JsonSnapshotDaemon): %(message)s"
)
logger = logging.getLogger("JsonSnapshotDaemon")

BACKUP_ROOT = ROOT_DIR / "Nexus_Backups" / "JSON_Snapshots"
EXCLUDE_DIRS = {
    "Nexus_Backups",
    "__pycache__",
    ".git",
    ".vscode",
    "ledger_archive",
    "Local-Backups",
    "Vault-Golden-Anchor",
}

class JsonSnapshotDaemon:
    def __init__(self, interval_minutes: int = 60, max_snapshots: int = 48):
        self.interval_seconds = interval_minutes * 60
        self.max_snapshots = max_snapshots
        self.ledger = NexusTradeLogger()
        self.notifier = TelegramNotifier()
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    def _discover_json_files(self) -> list[Path]:
        json_files = []
        for root, dirs, files in os.walk(ROOT_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith("BACKUP")]
            for file in files:
                if file.lower().endswith(".json"):
                    json_files.append(Path(root) / file)
        return json_files

    def _validate_json(self, file_path: Path) -> bool:
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                json.load(f)
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[SKIPPED CORRUPT/LOCKED JSON] {file_path.name}: {e}")
            return False

    def _enforce_retention(self):
        snapshots = sorted(
            [p for p in BACKUP_ROOT.iterdir() if p.is_dir() and p.name.startswith("snap_")],
            key=lambda p: p.name
        )
        while len(snapshots) > self.max_snapshots:
            oldest = snapshots.pop(0)
            shutil.rmtree(oldest, ignore_errors=True)
            logger.info(f"[RETENTION] Pruned old snapshot: {oldest.name}")

    def run_snapshot(self) -> dict:
        ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
        target_dir = BACKUP_ROOT / f"snap_{ts_label}"
        target_dir.mkdir(parents=True, exist_ok=True)

        json_files = self._discover_json_files()
        copied_count = 0
        skipped_count = 0

        for src_path in json_files:
            if not self._validate_json(src_path):
                skipped_count += 1
                continue

            rel_path = src_path.relative_to(ROOT_DIR)
            dest_path = target_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)
            copied_count += 1

        self._enforce_retention()

        self.ledger.log_telemetry(
            sleeve_id="SYSTEM_BACKUP",
            metric_name="json_snapshot_count",
            metric_value=float(copied_count),
            metadata=f"dir={target_dir.name} | skipped={skipped_count}"
        )

        logger.info(
            f"[SNAPSHOT COMPLETE] Archived {copied_count} valid JSON files -> {target_dir.name} "
            f"(Skipped: {skipped_count})"
        )
        return {"snapshot_dir": str(target_dir), "copied": copied_count, "skipped": skipped_count}

if __name__ == "__main__":
    daemon = JsonSnapshotDaemon(interval_minutes=60, max_snapshots=48)
    daemon.run_snapshot()
