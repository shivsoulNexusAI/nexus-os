from pathlib import Path

multi_path = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")
if not multi_path.exists():
    multi_path = Path(r"C:\Quant-Nexus-Prod\core\nexus_multi_straddle_daemon.py")

lines = multi_path.read_text(encoding="utf-8", errors="ignore").splitlines()
print("=" * 85)
print(f"INSPECTING CYCLE / ORDER PLACEMENT LOGIC ({multi_path.name})")
print("=" * 85)
for i in range(135, min(len(lines), 215)):
    print(f"{i+1:4d}: {lines[i]}")
print("=" * 85)