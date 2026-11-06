path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

patched = False
for idx in range(2000, min(len(lines), 2060)):
    line = lines[idx]
    if "Dashboard broadcast error" in line or "DASHBOARD_MSG_ID" in line:
        # Scan upward from the error handler to locate the broadcast attempt
        for k in range(idx - 1, max(0, idx - 20), -1):
            if "edit_message_text" in lines[k] or "send_message" in lines[k]:
                # Locate the parent try or if statement
                for t in range(k, max(0, k - 8), -1):
                    if lines[t].strip().startswith("try:") or "if DASHBOARD_MSG_ID" in lines[t]:
                        indent = " " * (len(lines[t]) - len(lines[t].lstrip()))
                        guard_snippet = (
                            f"{indent}if not board_text or not str(board_text).strip():\n"
                            f"{indent}    # Fallback to keep dashboard informative or bypass empty push\n"
                            f"{indent}    board_text = '⚡ <b>QUANT-NEXUS SENTINEL</b> | Autonomous Fleet Active'\n"
                        )
                        lines.insert(t, guard_snippet)
                        patched = True
                        print(f"[*] Injected non-empty text safeguard before line {t+1}")
                        break
                break
        if patched:
            break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"[+] Broadcast guard application status: {patched}")
