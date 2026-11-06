path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

trigger_idx = -1
for i, l in enumerate(lines):
    if "[INSTANT-TRIGGER]" in l:
        trigger_idx = i
        break

if trigger_idx == -1:
    print("[-] Could not find [INSTANT-TRIGGER] line.")
    exit(1)

start_idx = -1
for i in range(trigger_idx, max(0, trigger_idx - 35), -1):
    if "if cleared and not is_locked:" in lines[i]:
        start_idx = i
        break

if start_idx == -1:
    print("[-] Could not find 'if cleared and not is_locked:' line.")
    exit(1)

print(f"[+] Splicing lines {start_idx + 1} to {trigger_idx + 1}")

clean_replacement = [
    "                if cleared and not is_locked:\n",
    "                    sym = candidate.get('symbol')\n",
    "                    if not sym:\n",
    "                        continue\n",
    "                    if 'EXEC_COOLDOWNS' not in globals():\n",
    "                        globals()['EXEC_COOLDOWNS'] = {}\n",
    "                    import time as _t_mod\n",
    "                    _now_s = _t_mod.time()\n",
    "                    if sym in globals()['EXEC_COOLDOWNS'] and (_now_s - globals()['EXEC_COOLDOWNS'][sym]) < 300:\n",
    "                        continue\n",
    "                    globals()['EXEC_COOLDOWNS'][sym] = _now_s\n",
    "                    lots = candidate.get('calculated_lots', 0.01)\n",
    "                    sl = candidate.get('sl', 0.0)\n",
    "                    tp = candidate.get('tp', 0.0)\n",
    '                    print(f"[{t_now}] [INSTANT-TRIGGER] Firing {direction} on {sym} ({lots}L @ {edge}% Edge)...")\n'
]

new_lines = lines[:start_idx] + clean_replacement + lines[trigger_idx + 1:]

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("[+] Clean splice completed.")
