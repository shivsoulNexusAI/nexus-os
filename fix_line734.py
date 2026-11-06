path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "POSITION LOCK: Active trade already running" in line:
        print(f"[*] Found corrupted lock line at {i+1}: {repr(line)}")
        lines[i] = '        return "🛡️ POSITION LOCK: Active trade already running on " + sym + ".", None\n'

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Successfully repaired line 734.")
