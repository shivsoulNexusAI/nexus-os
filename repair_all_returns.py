target = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(target, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

repaired = []
for idx, line in enumerate(lines):
    # Detect line starting with return " or return ' where the string isn't closed on the same line
    stripped = line.strip()
    if (stripped.startswith('return "') or stripped.startswith("return '")) and not (stripped.endswith('"\n') or stripped.endswith("'\n") or stripped.endswith('"') or stripped.endswith("'")):
        # If it was an attempt to join card or msg list
        indent = len(line) - len(line.lstrip())
        spaces = " " * indent
        print(f"[*] Fixing broken return literal at line {idx + 1}: {stripped}")
        repaired.append(f"{spaces}return chr(10).join(card) if 'card' in locals() else chr(10).join(lines) if 'lines' in locals() else ''\n")
    else:
        repaired.append(line)

with open(target, "w", encoding="utf-8") as f:
    f.writelines(repaired)

print("[+] All broken return statements repaired.")
