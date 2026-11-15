from pathlib import Path
import time

log_multi = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.log")
log_be = Path(r"C:\Quant-Nexus-Prod\core\breakeven_engine.log")

print("=" * 85)
print("SILO 2 LIVE RUNTIME TELEMETRY (PID 8176 & PID 8944)")
print("=" * 85)

if log_multi.exists():
    lines = log_multi.read_text(encoding="utf-8", errors="ignore").splitlines()
    print(f"[+] nexus_multi_straddle_daemon.log ({len(lines)} total lines):")
    for l in lines[-8:]:
        print(f"    {l}")
else:
    print("[-] nexus_multi_straddle_daemon.log not found yet.")

print("-" * 85)
if log_be.exists():
    lines = log_be.read_text(encoding="utf-8", errors="ignore").splitlines()
    print(f"[+] breakeven_engine.log ({len(lines)} total lines):")
    for l in lines[-8:]:
        print(f"    {l}")
else:
    print("[-] breakeven_engine.log not found yet.")
print("=" * 85)