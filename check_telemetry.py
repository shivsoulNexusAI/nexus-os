import sqlite3

def check_telemetry():
    conn = sqlite3.connect("nexus_ledger.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== 1. RECENT ORDER INTENTS & VETO AUDITS ===")
    cursor.execute(
        """
        SELECT client_order_id, sleeve, symbol, state, created_utc 
        FROM order_intents 
        ORDER BY created_utc DESC 
        LIMIT 10;
        """
    )
    intents = cursor.fetchall()
    for row in intents:
        print(dict(row))

    print("\n=== 2. WORKER HEARTBEATS ===")
    try:
        cursor.execute("SELECT sleeve, login, pid, last_tick_utc, equity, status FROM worker_heartbeats;")
        heartbeats = cursor.fetchall()
        for hb in heartbeats:
            print(dict(hb))
    except Exception as e:
        print(f"Heartbeats table check note: {e}")
        
    conn.close()

if __name__ == "__main__":
    check_telemetry()
