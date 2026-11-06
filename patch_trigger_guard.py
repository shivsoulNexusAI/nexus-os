path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Locate line 439 where Firing is printed
f_idx = -1
for i in range(430, min(len(lines), 450)):
    if "[INSTANT-TRIGGER] Firing" in lines[i]:
        f_idx = i
        break

if f_idx == -1:
    print("[-] Could not find [INSTANT-TRIGGER] anchor.")
    exit(1)

print(f"[*] Found trigger execution anchor at line {f_idx + 1}")

# Locate if ok:
ok_idx = -1
for j in range(f_idx, min(len(lines), f_idx + 10)):
    if lines[j].strip().startswith("if ok:"):
        ok_idx = j
        break

if ok_idx != -1:
    indent = " " * (len(lines[f_idx]) - len(lines[f_idx].lstrip()))
    
    # Replace lines from f_idx to ok_idx with safe unpack, execution tracking, and failure logging
    replacement = [
        f"{lines[f_idx]}",
        f"{indent}_raw = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)\n",
        f"{indent}if isinstance(_raw, (tuple, list)):\n",
        f"{indent}    ok = bool(_raw[0]) if len(_raw) > 0 else False\n",
        f"{indent}    res_msg = str(_raw[1]) if len(_raw) > 1 else ''\n",
        f"{indent}    ticket = _raw[2] if len(_raw) > 2 else None\n",
        f"{indent}else:\n",
        f"{indent}    ok, res_msg, ticket = False, str(_raw or ''), None\n",
        f"\n",
        f"{indent}if not ok and res_msg:\n",
        f"{indent}    print(f'[{t_now}] [INSTANT-TRIGGER] {sym} order rejected/failed: {res_msg}')\n",
        f"\n"
    ]
    
    # We replace from line f_idx to ok_idx (exclusive of ok_idx)
    lines = lines[:f_idx] + replacement + lines[ok_idx:]
    
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("[+] Trigger execution guard and failure logger installed.")
else:
    print("[-] Could not find `if ok:` anchor.")
