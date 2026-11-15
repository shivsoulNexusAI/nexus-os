import psutil
from pathlib import Path

print("=" * 85)
print("ACTIVE MT5 PROCESSES & INSTANCE BINDINGS")
print("=" * 85)

for p in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
    try:
        if "terminal64" in p.info['name'].lower():
            exe_path = p.info['exe'] or "Unknown"
            cmd = " ".join(p.info['cmdline'] or [])
            print(f"PID: {p.info['pid']:<6} | EXE: {exe_path}")
            print(f"       CMD: {cmd}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

print("=" * 85)