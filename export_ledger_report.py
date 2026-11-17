# =====================================================================
# SHIVSOUL NEXUS v7.0 // LEDGER CSV TELEMETRY EXPORTER
# =====================================================================
import sqlite3
import csv
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("nexus_ledger.db")
OUTPUT_DIR = Path(r"C:\Quant-Nexus-Eng\reports")

def export_ledger_reports():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    if not DB_PATH.exists():
        print(f"[ERR] Database not found at {DB_PATH.absolute()}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM order_intents ORDER BY created_utc DESC;")
        intents = cursor.fetchall()
        if intents:
            intents_file = OUTPUT_DIR / f"order_intents_audit_{timestamp}.csv"
            with open(intents_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(intents[0].keys())
                for row in intents:
                    writer.writerow(row)
            print(f"[SUCCESS] Exported {len(intents)} order intents to: {intents_file}")
        else:
            print("[INFO] No order intents found to export.")
    except Exception as e:
        print(f"[WARN] Could not export order_intents: {e}")

    try:
        cursor.execute("SELECT * FROM managed_positions;")
        positions = cursor.fetchall()
        if positions:
            positions_file = OUTPUT_DIR / f"managed_positions_{timestamp}.csv"
            with open(positions_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(positions[0].keys())
                for row in positions:
                    writer.writerow(row)
            print(f"[SUCCESS] Exported {len(positions)} managed positions to: {positions_file}")
        else:
            print("[INFO] No managed positions table or records found to export.")
    except Exception as e:
        print(f"[WARN] Could not export managed_positions: {e}")

    conn.close()

if __name__ == "__main__":
    export_ledger_reports()
