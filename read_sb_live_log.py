from pathlib import Path

# [DISABLED_V44] log_path = Path(r"C:\Quant-Nexus-Eng\silver_bullet_daemon.log")
# [DISABLED_V44] err_path = Path(r"C:\Quant-Nexus-Eng\silver_bullet_daemon_err.log")

print("=" * 85)
print("SILVER BULLET LIVE LOG STREAM (PID 2312 - LIVE-ARMED)")
print("=" * 85)

if log_path.exists():
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-25:]
    print("--- Recent stdout entries ---")
    for l in lines:
        print(f"  {l}")
else:
    # [DISABLED_V44] print("[-] silver_bullet_daemon.log not found.")

if err_path.exists():
    err_lines = err_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-10:]
    if err_lines:
        print("-" * 85)
        print("--- Recent stderr entries ---")
        for el in err_lines:
            print(f"  {el}")
print("=" * 85)
