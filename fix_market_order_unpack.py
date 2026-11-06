path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# 1. Patch call site around line 1955
patched_call = False
for idx in range(max(0, 1940), min(len(lines), 1970)):
    if "execute_market_order" in lines[idx] and "=" in lines[idx]:
        indent = " " * (len(lines[idx]) - len(lines[idx].lstrip()))
        print(f"[*] Patching call site at line {idx+1}: {lines[idx].strip()}")
        lines[idx] = (
            f"{indent}_raw = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)\n"
            f"{indent}if isinstance(_raw, (tuple, list)):\n"
            f"{indent}    ok = bool(_raw[0]) if len(_raw) > 0 else False\n"
            f"{indent}    res_msg = str(_raw[1]) if len(_raw) > 1 else ''\n"
            f"{indent}    ticket = _raw[2] if len(_raw) > 2 else None\n"
            f"{indent}else:\n"
            f"{indent}    ok, res_msg, ticket = False, str(_raw or ''), None\n"
        )
        patched_call = True
        break

# 2. Patch execute_market_order definition returns
in_func = False
func_indent = 0
patched_returns = 0
for idx, line in enumerate(lines):
    if "def execute_market_order(" in line:
        in_func = True
        func_indent = len(line) - len(line.lstrip())
        print(f"[*] Found execute_market_order at line {idx+1}")
        continue
    
    if in_func:
        if line.strip() and not line.startswith(" " * (func_indent + 1)):
            in_func = False
            continue
        
        stripped = line.strip()
        cur_indent = " " * (len(line) - len(line.lstrip()))
        if stripped in ("return", "return None"):
            lines[idx] = f"{cur_indent}return False, 'Order aborted', None\n"
            patched_returns += 1
        elif stripped.startswith("return ") and stripped.count(",") == 1:
            val = stripped[7:]
            lines[idx] = f"{cur_indent}return {val}, None\n"
            patched_returns += 1

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"[+] Call site patched: {patched_call} | Function returns patched: {patched_returns}")
