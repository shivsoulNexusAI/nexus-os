path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("--- LOCATING CALL SITES & FUNCTIONS ---")
for idx, line in enumerate(lines):
    if "Executing full universe evaluation" in line or "[INSTANT-TRIGGER]" in line:
        print(f"\n[Line {idx+1}] {line.strip()}")
        # Print next 10 lines of the call site
        for k in range(idx + 1, min(len(lines), idx + 12)):
            print(f"  {k+1:04d}: {lines[k].rstrip()}")
