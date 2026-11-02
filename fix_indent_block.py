path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Target lines 1945 to 1975
start_idx = -1
for i in range(max(0, 1940), min(len(lines), 1980)):
    if "[INSTANT-TRIGGER]" in lines[i]:
        start_idx = i
        break

if start_idx != -1:
    print(f"[*] Found INSTANT-TRIGGER at line {start_idx + 1}")
    # Find where if ok: begins
    end_idx = -1
    for j in range(start_idx, min(len(lines), start_idx + 35)):
        if lines[j].strip().startswith("if ok:"):
            end_idx = j
            break
            
    if end_idx != -1:
        # Determine exact indentation from the print line
        indent = " " * (len(lines[start_idx]) - len(lines[start_idx].lstrip()))
        clean_block = [
            lines[start_idx],
            f"{indent}_raw = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)\n",
            f"{indent}if isinstance(_raw, (tuple, list)):\n",
            f"{indent}    ok = bool(_raw[0]) if len(_raw) > 0 else False\n",
            f"{indent}    res_msg = str(_raw[1]) if len(_raw) > 1 else ''\n",
            f"{indent}    ticket = _raw[2] if len(_raw) > 2 else None\n",
            f"{indent}else:\n",
            f"{indent}    ok, res_msg, ticket = False, str(_raw or ''), None\n"
        ]
        lines = lines[:start_idx] + clean_block + lines[end_idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("[+] Successfully reconstructed execution block with correct indentation.")
    else:
        print("[-] Could not find 'if ok:' anchor.")
else:
    print("[-] Could not find INSTANT-TRIGGER anchor.")
