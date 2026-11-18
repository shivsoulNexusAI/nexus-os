import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from vpin_filter import VPINToxicityFilter

class MacroGateController:
    def __init__(self, db_path: str = "nexus_ledger.db", vpin_threshold: float = 0.75):
        self.db_path = Path(db_path)
        self.vpin_guard = VPINToxicityFilter(bucket_volume=10.0, window_size=30, toxicity_threshold=vpin_threshold)

    def _log_veto(self, symbol: str, sleeve: str, reason: str):
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA table_info(order_intents);")
            table_info = cursor.fetchall()
            columns = {col[1]: {"not_null": col[3], "dflt": col[4]} for col in table_info}

            # Use UUID hex suffix to ensure absolute uniqueness across rapid multi-sleeve evaluations
            timestamp_id = f"VETO_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:6]}"
            now_iso = datetime.now(timezone.utc).isoformat()

            payload = {
                "client_order_id": timestamp_id,
                "sleeve": sleeve,
                "symbol": symbol,
                "direction": "FLAT",
                "volume": 0.0,
                "score": 0.0,
                "state": f"REJECTED_{reason}",
                "entry_req": "GATE_VETO",
                "init_sl": 0.0,
                "init_tp": 0.0,
                "created_utc": now_iso
            }

            insert_cols = []
            insert_vals = []
            
            for col_name, meta in columns.items():
                if col_name in payload:
                    insert_cols.append(col_name)
                    insert_vals.append(payload[col_name])
                elif meta["not_null"] == 1 and meta["dflt"] is None:
                    insert_cols.append(col_name)
                    insert_vals.append(0.0 if "REAL" in str(col_name).upper() or "INT" in str(col_name).upper() else "")

            cols_str = ", ".join(insert_cols)
            placeholders = ", ".join(["?"] * len(insert_vals))
            
            cursor.execute(f"INSERT INTO order_intents ({cols_str}) VALUES ({placeholders});", tuple(insert_vals))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[WARN] Failed to log VETO to SQLite WAL: {e}")

    def evaluate_gate(self, symbol: str, sleeve: str = "T1") -> dict:
        now_utc = datetime.now(timezone.utc)
        utc_hr = now_utc.hour
        utc_min = now_utc.minute

        if utc_hr == 13 and 15 <= utc_min <= 35:
            reason = "NEWS_BLACKOUT_WINDOW"
            self._log_veto(symbol, sleeve, reason)
            return {"allowed": False, "reason": reason}

        toxicity_res = self.vpin_guard.compute_vpin(symbol)
        if toxicity_res.get("is_toxic", False):
            vpin_val = toxicity_res.get("vpin", 0.0)
            threshold = toxicity_res.get("threshold", 0.75)
            reason = f"VPIN_TOXICITY_VETO (VPIN={vpin_val:.2f}>={threshold})"
            self._log_veto(symbol, sleeve, reason)
            return {"allowed": False, "reason": reason}

        return {"allowed": True, "reason": "MACRO_CLEAR"}
