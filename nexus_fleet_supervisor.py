import subprocess
import sys
import time
from datetime import datetime, timezone
from nexus_wal_ledger import init_ledger, get_conn

SLEEVE_ORDER = ["T1", "T2", "T3"]

def spawn_worker(sleeve: str) -> subprocess.Popen:
    cmd = [sys.executable, "nexus_sleeve_worker.py", sleeve]
    proc = subprocess.Popen(cmd)
    print(f"[SUPERVISOR] Spawned {sleeve} worker (PID={proc.pid})")
    return proc

def main() -> None:
    init_ledger()
    procs = {s: spawn_worker(s) for s in SLEEVE_ORDER}

    try:
        while True:
            time.sleep(5.0)
            now = datetime.now(timezone.utc)
            conn = get_conn()
            hb_rows = {r["sleeve"]: dict(r) for r in conn.execute("SELECT * FROM worker_heartbeats;").fetchall()}
            conn.close()

            for s in SLEEVE_ORDER:
                p = procs[s]
                dead = (p.poll() is not None)
                stale = False
                if s in hb_rows:
                    last_tick = datetime.fromisoformat(hb_rows[s]["last_tick_utc"])
                    if (now - last_tick).total_seconds() > 12.0:
                        stale = True

                if dead or stale:
                    reason = f"exited({p.returncode})" if dead else "heartbeat_stale(>12s)"
                    print(f"[SUPERVISOR ALERT] {s} worker {reason} — restarting...")
                    if not dead:
                        p.kill()
                    procs[s] = spawn_worker(s)
    except KeyboardInterrupt:
        print("\n[SUPERVISOR] Shutting down fleet workers cleanly...")
        for p in procs.values():
            p.terminate()

if __name__ == "__main__":
    main()
