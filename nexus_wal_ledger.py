import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_ledger.db")

USD_FACTOR_SIGN = {
    "EURUSD": -1.0, "GBPUSD": -1.0, "AUDUSD": -1.0, "XAUUSD": -1.0,
    "USDCAD": +1.0, "USDJPY": +1.0,
    "GBPJPY":  0.0, "BTCUSD":  0.0,
}

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_ledger() -> None:
    conn = get_conn()
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
            sleeve        TEXT PRIMARY KEY,
            pid           INTEGER NOT NULL,
            login         INTEGER NOT NULL,
            equity        REAL NOT NULL,
            open_count    INTEGER NOT NULL,
            last_tick_utc TEXT NOT NULL,
            last_scan_utc TEXT,
            status        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_intents (
            client_order_id TEXT PRIMARY KEY,
            sleeve          TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            direction       TEXT NOT NULL,
            volume          REAL NOT NULL,
            entry_req       REAL NOT NULL,
            init_sl         REAL NOT NULL,
            init_tp         REAL NOT NULL,
            score           REAL NOT NULL,
            regime_json     TEXT NOT NULL,
            state           TEXT NOT NULL,
            mt5_ticket      INTEGER,
            fill_price      REAL,
            slippage_pts    REAL,
            created_utc     TEXT NOT NULL,
            updated_utc     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS managed_positions (
            ticket          INTEGER PRIMARY KEY,
            sleeve          TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            direction       TEXT NOT NULL,
            volume          REAL NOT NULL,
            entry_price     REAL NOT NULL,
            init_sl         REAL NOT NULL,
            current_sl      REAL NOT NULL,
            current_tp      REAL NOT NULL,
            be_locked       INTEGER NOT NULL DEFAULT 0,
            peak_r          REAL NOT NULL DEFAULT 0.0,
            usd_beta        REAL NOT NULL DEFAULT 0.0,
            opened_utc      TEXT NOT NULL,
            updated_utc     TEXT NOT NULL
        );
        """)
    finally:
        conn.close()

def upsert_heartbeat(sleeve: str, pid: int, login: int, equity: float, open_count: int, status: str, scan_ts: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute("""
            INSERT INTO worker_heartbeats (sleeve, pid, login, equity, open_count, last_tick_utc, last_scan_utc, status)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, ?), ?)
            ON CONFLICT(sleeve) DO UPDATE SET
                pid=excluded.pid,
                equity=excluded.equity,
                open_count=excluded.open_count,
                last_tick_utc=excluded.last_tick_utc,
                last_scan_utc=COALESCE(?, worker_heartbeats.last_scan_utc),
                status=excluded.status;
        """, (sleeve, pid, login, equity, open_count, now, scan_ts, now, status, scan_ts))
        conn.execute("COMMIT;")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()

def reserve_order_intent(client_order_id: str, sleeve: str, symbol: str, direction: str,
                         volume: float, entry_req: float, init_sl: float, init_tp: float,
                         score: float, regime: dict, max_net_usd_beta: float = 1.5) -> tuple[bool, str]:
    now = datetime.now(timezone.utc).isoformat()
    sign = 1.0 if direction == "BUY" else -1.0
    proposed_beta = USD_FACTOR_SIGN.get(symbol, 0.0) * sign

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        row = conn.execute("SELECT COALESCE(SUM(usd_beta), 0.0) AS net_beta FROM managed_positions;").fetchone()
        current_beta = float(row["net_beta"])
        if abs(current_beta + proposed_beta) > max_net_usd_beta and proposed_beta != 0.0:
            conn.execute("ROLLBACK;")
            return False, f"USD_FACTOR_CAP ({current_beta:+.1f} + {proposed_beta:+.1f} > {max_net_usd_beta:.1f})"

        conn.execute("""
            INSERT INTO order_intents (
                client_order_id, sleeve, symbol, direction, volume, entry_req,
                init_sl, init_tp, score, regime_json, state, created_utc, updated_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'INTENT', ?, ?);
        """, (client_order_id, sleeve, symbol, direction, volume, entry_req,
              init_sl, init_tp, score, json.dumps(regime), now, now))
        conn.execute("COMMIT;")
        return True, "RESERVED"
    except sqlite3.IntegrityError:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        return False, "DUPLICATE_CLIENT_ORDER_ID"
    except Exception as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        return False, f"DB_ERR: {exc}"
    finally:
        conn.close()

def finalize_order_fill(client_order_id: str, ticket: int, fill_price: float, slippage_pts: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        intent = conn.execute("SELECT * FROM order_intents WHERE client_order_id = ?;", (client_order_id,)).fetchone()
        if intent:
            sign = 1.0 if intent["direction"] == "BUY" else -1.0
            beta = USD_FACTOR_SIGN.get(intent["symbol"], 0.0) * sign
            conn.execute("""
                UPDATE order_intents
                SET state='FILLED', mt5_ticket=?, fill_price=?, slippage_pts=?, updated_utc=?
                WHERE client_order_id=?;
            """, (ticket, fill_price, slippage_pts, now, client_order_id))
            conn.execute("""
                INSERT OR REPLACE INTO managed_positions (
                    ticket, sleeve, symbol, direction, volume, entry_price,
                    init_sl, current_sl, current_tp, be_locked, peak_r, usd_beta, opened_utc, updated_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0.0, ?, ?, ?);
            """, (ticket, intent["sleeve"], intent["symbol"], intent["direction"], intent["volume"],
                  fill_price, intent["init_sl"], intent["init_sl"], intent["init_tp"], beta, now, now))
        conn.execute("COMMIT;")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()

def sync_open_positions(sleeve: str, live_tickets: dict[int, dict]) -> dict[int, dict]:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    merged = {}
    try:
        conn.execute("BEGIN IMMEDIATE;")
        existing = {
            r["ticket"]: dict(r)
            for r in conn.execute("SELECT * FROM managed_positions WHERE sleeve = ?;", (sleeve,)).fetchall()
        }
        for tkt in set(existing.keys()) - set(live_tickets.keys()):
            conn.execute("DELETE FROM managed_positions WHERE ticket = ?;", (tkt,))
            conn.execute("UPDATE order_intents SET state='CLOSED', updated_utc=? WHERE mt5_ticket=?;", (now, tkt))

        for tkt, pos in live_tickets.items():
            if tkt in existing:
                row = existing[tkt]
                row["current_sl"] = pos["sl"]
                row["current_tp"] = pos["tp"]
                conn.execute("""
                    UPDATE managed_positions SET current_sl=?, current_tp=?, updated_utc=? WHERE ticket=?;
                """, (pos["sl"], pos["tp"], now, tkt))
                merged[tkt] = row
            else:
                sign = 1.0 if pos["direction"] == "BUY" else -1.0
                beta = USD_FACTOR_SIGN.get(pos["raw_symbol"], 0.0) * sign
                be_flag = 1 if ((pos["direction"] == "BUY" and pos["sl"] >= pos["entry"]) or
                                (pos["direction"] == "SELL" and 0 < pos["sl"] <= pos["entry"])) else 0
                conn.execute("""
                    INSERT INTO managed_positions (
                        ticket, sleeve, symbol, direction, volume, entry_price,
                        init_sl, current_sl, current_tp, be_locked, peak_r, usd_beta, opened_utc, updated_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?);
                """, (tkt, sleeve, pos["raw_symbol"], pos["direction"], pos["volume"],
                      pos["entry"], pos["init_sl"], pos["sl"], pos["tp"], be_flag, beta, now, now))
                merged[tkt] = {
                    "ticket": tkt, "entry_price": pos["entry"], "init_sl": pos["init_sl"],
                    "current_sl": pos["sl"], "current_tp": pos["tp"], "be_locked": be_flag, "peak_r": 0.0
                }
        conn.execute("COMMIT;")
        return merged
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()

def mark_be_locked(ticket: int, new_sl: float, peak_r: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute("""
            UPDATE managed_positions SET current_sl=?, be_locked=1, peak_r=MAX(peak_r, ?), updated_utc=? WHERE ticket=?;
        """, (new_sl, peak_r, now, ticket))
        conn.execute("UPDATE order_intents SET state='BE_LOCKED', updated_utc=? WHERE mt5_ticket=?;", (now, ticket))
        conn.execute("COMMIT;")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()
