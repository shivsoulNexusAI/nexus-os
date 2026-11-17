import sqlite3

def audit_ledger():
    conn = sqlite3.connect("nexus_ledger.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT client_order_id, sleeve, symbol, state, created_utc 
        FROM order_intents 
        WHERE state LIKE '%VETO%' 
        ORDER BY created_utc DESC;
        """
    )
    rows = cursor.fetchall()
    print(f"=== SQLite WAL Ledger: VPIN Veto Records ({len(rows)} found) ===")
    for r in rows:
        print(dict(r))
        
    conn.close()

if __name__ == "__main__":
    audit_ledger()
