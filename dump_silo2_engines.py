from pathlib import Path

multi_path = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")
if not multi_path.exists():
    multi_path = Path(r"C:\Quant-Nexus-Prod\core\nexus_multi_straddle_daemon.py")

be_path = Path(r"C:\Quant-Nexus-Prod\core\breakeven_engine.py")
if not be_path.exists():
    be_path = Path(r"C:\Quant-Nexus-Eng\breakeven_engine.py")

print("=" * 85)
print(f"PART 1: FULL CODE OVERVIEW OF {multi_path.name}")
print("=" * 85)
multi_lines = multi_path.read_text(encoding="utf-8", errors="ignore").splitlines()
for i, l in enumerate(multi_lines):
    if l.strip().startswith("def ") or l.strip().startswith("class ") or any(k in l for k in ["SYMBOL", "MAGIC", "ORDER", "OFFSET", "TP", "SL", "LOT"]):
        print(f"{i+1:4d}: {l}")

print("\n" + "=" * 85)
print(f"PART 2: BREAKEVEN & HARVEST ENGINE LOGIC ({be_path.name})")
print("=" * 85)
be_lines = be_path.read_text(encoding="utf-8", errors="ignore").splitlines()
for i in range(40, min(len(be_lines), 170)):
    print(f"{i+1:4d}: {be_lines[i]}")
print("=" * 85)