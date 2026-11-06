path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

patched = False
for idx in range(2000, min(len(lines), 2050)):
    line = lines[idx]
    if "edit_message_text" in line or "send_message" in line:
        if "board_text" in line:
            # Locate the check before the broadcast
            # Inject a fallback check right above if not present
            for k in range(max(0, idx - 8), idx):
                if "if not board_text" in lines[k] or "if board_text" in lines[k]:
                    break
            else:
                indent = " " * (len(line) - len(line.lstrip()))
                guard = f"{indent}if not board_text or not str(board_text).strip():\n{indent}    continue\n"
                # Place before the try block surrounding edit_message_text
                for t in range(idx, max(0, idx - 6), -1):
                    if lines[t].strip().startswith("try:"):
                        t_indent = " " * (len(lines[t]) - len(lines[t].lstrip()))
                        lines[t] = f"{t_indent}if not board_text or not str(board_text).strip():\n{t_indent}    continue\n{lines[t]}"
                        patched = True
                        print(f"[*] Added non-empty check before broadcast at line {t+1}")
                        break
        if patched:
            break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"[+] Broadcast empty check applied: {patched}")
