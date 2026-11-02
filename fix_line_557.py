path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

new_lines = []
skip_broken = False

for i, l in enumerate(lines):
    # Detect the broken unterminated f-string around line 555-560
    if ('lines.append(f"' in l or "lines.append(f'" in l) and "Last Scanned" not in l and i > 540 and i < 570:
        # Check if this line or next has the broken timestamp
        lookahead = "".join(lines[i:min(len(lines), i+4)])
        if "Last Scanned" in lookahead:
            new_lines.append('    lines.append(f"\\n⏱️ Last Scanned: {t_now}")\n')
            skip_broken = True
            continue

    if skip_broken:
        if "return " in l:
            skip_broken = False
            new_lines.append(l)
        continue

    new_lines.append(l)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("[+] Repaired unterminated f-string at line 557.")
