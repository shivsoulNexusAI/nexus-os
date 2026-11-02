path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# 1. Remove previously injected lines that caused indentation errors
filtered = []
for l in lines:
    if any(marker in l for marker in [
        "# Safe symbol resolution guard",
        "locals().get('target_symbol')",
        "isinstance(candidate, dict)",
        "EXECUTION_COOLDOWN_MAP",
        "COOLDOWN_SECONDS",
        "_target = symbol",
        "sym = None",
        "_var in ['symbol'",
        "attempted_cooldown"
    ]):
        continue
    filtered.append(l)

# 2. Locate the line with [INSTANT-TRIGGER]
trigger_idx = -1
for idx, line in enumerate(filtered):
    if "[INSTANT-TRIGGER]" in line:
        trigger_idx = idx
        break

if trigger_idx != -1:
    # Detect the exact whitespace of the line containing [INSTANT-TRIGGER]
    trigger_line = filtered[trigger_idx]
    ws = trigger_line[:len(trigger_line) - len(trigger_line.lstrip(" "))]
    
    # Check if sym is already safely defined right above
    prev_lines = "".join(filtered[max(0, trigger_idx - 5):trigger_idx])
    if "sym =" not in prev_lines:
        safe_injection = [
            f"{ws}# Resolved symbol definition\n",
            f"{ws}sym = symbol if 'symbol' in locals() else (candidate.get('symbol') if 'candidate' in locals() and isinstance(candidate, dict) else None)\n"
        ]
        filtered = filtered[:trigger_idx] + safe_injection + filtered[trigger_idx:]
        print(f"[+] Injected sym definition with {len(ws)} leading spaces before line {trigger_idx + 1}.")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(filtered)

print("[+] Cleaned and formatted telegram_interactive.py.")
