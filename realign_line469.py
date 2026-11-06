path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i in range(max(0, 460), min(len(lines), 475)):
    if "if DASHBOARD_MSG_ID:" in lines[i]:
        # Determine base indent from preceding line or function block
        prev_indent = ""
        for prev in range(i - 1, max(0, i - 10), -1):
            if lines[prev].strip() and not lines[prev].strip().startswith("#"):
                prev_indent = " " * (len(lines[prev]) - len(lines[prev].lstrip()))
                break
        
        target_indent = prev_indent if prev_indent else "    "
        print(f"[*] Correcting line {i+1} indent from {len(lines[i]) - len(lines[i].lstrip())} spaces to {len(target_indent)} spaces")
        lines[i] = f"{target_indent}if DASHBOARD_MSG_ID:\n"
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)
