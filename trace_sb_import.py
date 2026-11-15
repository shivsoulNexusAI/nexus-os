from pathlib import Path
import re

# [DISABLED_V44] script_path = Path(r"C:\Quant-Nexus-Eng\silver_bullet_daemon.py")
code = script_path.read_text(encoding="utf-8", errors="ignore")

print("=" * 85)
print("TRACING route_silver_bullet_order IMPORT ORIGIN")
print("=" * 85)

for line in code.splitlines():
    if "route_silver_bullet_order" in line and ("import" in line or "from" in line):
        print(f"[+] Import Statement: {line.strip()}")

# Tail the last 15 lines of silver_bullet_daemon.log to confirm LIVE-ARMED initialization
# [DISABLED_V44] log_path = Path(r"C:\Quant-Nexus-Eng\silver_bullet_daemon.log")
if log_path.exists():
    print("-" * 85)
    # [DISABLED_V44] print("LIVE LOG TAIL (silver_bullet_daemon.log):")
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-15:]
    for l in lines:
        print(f"  {l}")
print("=" * 85)
