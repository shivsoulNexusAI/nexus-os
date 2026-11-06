path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Target line 614 (0-based index 613)
target_idx = 613
if target_idx < len(lines):
    if_line = lines[target_idx]
    base_indent = " " * (len(if_line) - len(if_line.lstrip()))
    body_indent = base_indent + "    "
    
    # Check lines immediately following line 614
    for next_idx in range(target_idx + 1, min(len(lines), target_idx + 5)):
        stripped = lines[next_idx].strip()
        if stripped:
            lines[next_idx] = body_indent + stripped + "\n"
            print(f"[+] Re-indented line {next_idx + 1}: {repr(lines[next_idx])}")
            break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Successfully aligned block after line 614.")
