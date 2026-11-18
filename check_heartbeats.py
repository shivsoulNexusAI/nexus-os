import sqlite3

def audit_heartbeats_and_positions():
    conn = sqlite3.connect("nexus_ledger.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== 1. WORKER HEARTBEATS ===")
    try:
        cursor.execute("SELECT sleeve, login, pid, last_tick_utc, equity, status FROM worker_heartbeats ORDER BY last_tick_utc DESC;")
        hb_rows = cursor.fetchall()
        if hb_rows:
            for r in hb_rows:
                print(dict(r))
        else:
            print("[INFO] No worker heartbeats recorded yet.")
    except Exception as e:
        print(f"[NOTE] worker_heartbeats table query note: {e}")

    print("\n=== 2. MANAGED POSITIONS ===")
    try:
        cursor.execute("SELECT * FROM managed_positions;")
        pos_rows = cursor.fetchall()
        if pos_rows:
            for r in pos_rows:
                print(dict(r))
        else:
            print("[INFO] No active managed positions recorded.")
    except Exception as e:
        print(f"[NOTE] managed_positions table query note: {e}")
        
    conn.close()

if __name__ == "__main__":
    audit_heartbeats_and_positions()
