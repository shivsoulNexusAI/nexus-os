path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i in range(460, min(len(lines), 480)):
    if "if board_text and str(board_text).strip():" in lines[i]:
        # Check if line i+1 is an unindented if DASHBOARD_MSG_ID
        if i + 1 < len(lines) and "if DASHBOARD_MSG_ID:" in lines[i+1]:
            indent = " " * (len(lines[i+1]) - len(lines[i+1].lstrip()))
            print(f"[*] Removing misplaced guard at line {i+1}")
            lines.pop(i)
            break
        elif "if DASHBOARD_MSG_ID:" in lines[i]:
            # It was inserted on the same line
            indent = " " * (len(lines[i]) - len(lines[i].lstrip()))
            lines[i] = f"{indent}if DASHBOARD_MSG_ID:\n"
            print(f"[*] Reverted line {i+1} back to clean condition")
            break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)
