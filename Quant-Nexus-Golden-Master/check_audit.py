import sqlite3

conn = sqlite3.connect("quant_metrics.db")
cur = conn.cursor()

query = """
SELECT audit_id, user_id, action, status, datetime(timestamp, 'unixepoch')
FROM nexus_c2_audit
ORDER BY audit_id DESC
LIMIT 10
"""

cur.execute(query)
rows = cur.fetchall()

print(f"{'ID':<4} {'USER_ID':<12} {'ACTION':<22} {'STATUS':<25} {'TIME_UTC':<20}")
print("-" * 88)
for r in rows:
    print(f"{r[0]:<4} {str(r[1]):<12} {r[2]:<22} {r[3]:<25} {r[4]:<20}")

conn.close()
