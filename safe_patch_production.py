path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

new_lines = []
skip_until_next_def = False
injected_ensure = False
sym_guaranteed = False

for i, line in enumerate(lines):
    # 1. Update ensure_mt5 cleanly
    if line.startswith("def ensure_mt5():") or line.strip() == "def ensure_mt5():":
        new_lines.append("def ensure_mt5():\n")
        new_lines.append("    try:\n")
        new_lines.append("        if not mt5.terminal_info() or not mt5.account_info() or mt5.account_info().login != 278025377:\n")
        new_lines.append('            term_p = "C:/Program Files/MetaTrader 5/terminal64.exe"\n')
        new_lines.append('            return mt5.initialize(path=term_p, login=278025377, password="H@ngkook3695", server="Exness-MT5Trial5", timeout=60000)\n')
        new_lines.append("        return True\n")
        new_lines.append("    except Exception:\n")
        new_lines.append("        return False\n\n")
        skip_until_next_def = True
        injected_ensure = True
        continue

    if skip_until_next_def:
        if line.startswith("def ") or line.startswith("class ") or line.startswith("async def "):
            skip_until_next_def = False
        else:
            continue

    # 2. Inject sym guarantee right before [INSTANT-TRIGGER]
    if "[INSTANT-TRIGGER]" in line and "sym" not in lines[max(0, i-2)]:
        indent = line[:len(line) - len(line.lstrip(" "))]
        new_lines.append(f"{indent}sym = candidate.get('symbol') if isinstance(candidate, dict) else getattr(candidate, 'symbol', None)\n")
        new_lines.append(f"{indent}if not sym: continue\n")
        new_lines.append(f"{indent}if 'EXEC_COOLDOWNS' not in globals(): globals()['EXEC_COOLDOWNS'] = {{}}\n")
        new_lines.append(f"{indent}import time as _t_mod; _now_s = _t_mod.time()\n")
        new_lines.append(f"{indent}if sym in globals()['EXEC_COOLDOWNS'] and (_now_s - globals()['EXEC_COOLDOWNS'][sym]) < 300: continue\n")
        new_lines.append(f"{indent}globals()['EXEC_COOLDOWNS'][sym] = _now_s\n")
        sym_guaranteed = True

    new_lines.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print(f"[+] ensure_mt5 replaced: {injected_ensure}")
print(f"[+] sym guarantee injected: {sym_guaranteed}")
