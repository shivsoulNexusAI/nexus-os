from pathlib import Path

be_path = Path(r"C:\Quant-Nexus-Prod\core\breakeven_engine.py")
if not be_path.exists():
    be_path = Path(r"C:\Quant-Nexus-Eng\breakeven_engine.py")

lines = be_path.read_text(encoding="utf-8", errors="ignore").splitlines()
print("=" * 85)
print(f"INSPECTING REMAINDER OF breakeven_engine.py (LINES 170-250)")
print("=" * 85)
for i in range(169, min(len(lines), 250)):
    print(f"{i+1:4d}: {lines[i]}")
print("=" * 85)