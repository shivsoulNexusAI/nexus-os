path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

patched = False
for idx in range(2015, min(len(lines), 2050)):
    # Replace continue under the empty board_text check with pass or structured if
    if "if not board_text or not str(board_text).strip():" in lines[idx]:
        indent = " " * (len(lines[idx]) - len(lines[idx].lstrip()))
        print(f"[*] Found runaway continue at line {idx+1}")
        
        # Replace the check so that broadcast only runs if board_text exists, without aborting the loop
        lines[idx] = f"{indent}if board_text and str(board_text).strip():\n"
        # Find where continue was placed
        if idx + 1 < len(lines) and "continue" in lines[idx + 1]:
            lines.pop(idx + 1)
        
        # Re-indent the broadcast block under this condition
        # Locate from idx+1 to the end of the broadcast try/except
        k = idx + 1
        while k < len(lines) and k < idx + 30:
            if "asyncio.sleep" in lines[k] or "except " in lines[k] and "dbe" not in lines[k]:
                break
            if lines[k].strip():
                lines[k] = "    " + lines[k]
            k += 1
        patched = True
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"[+] Fixed loop spin condition: {patched}")
