path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# 1. Strip out the previously injected lines that caused line 888 crash
cleaned = []
for line in lines:
    if any(marker in line for marker in [
        "# Safe symbol resolution guard",
        "locals().get('target_symbol')",
        "isinstance(candidate, dict)",
        "EXECUTION_COOLDOWN_MAP = {}",
        "EXECUTION_COOLDOWN_MAP[_target]"
    ]):
        continue
    cleaned.append(line)

# 2. Find the trigger loop line and detect its exact leading whitespace
target_idx = -1
indent = "        " # default 8 spaces
for idx, line in enumerate(cleaned):
    if "[INSTANT-TRIGGER]" in line:
        target_idx = idx
        indent = line[:len(line) - len(line.lstrip(" "))]
        break

if target_idx != -1:
    # Safely define sym matching exact indentation right above the trigger
    fix_lines = [
        f"{indent}sym = locals().get('symbol') or locals().get('target_symbol') or locals().get('s')\n",
        f"{indent}if not sym and 'candidate' in locals():\n",
        f"{indent}    sym = candidate.get('symbol') if isinstance(candidate, dict) else getattr(candidate, 'symbol', None)\n",
    ]
    # Insert safely right above the [INSTANT-TRIGGER] line
    cleaned = cleaned[:target_idx] + fix_lines + cleaned[target_idx:]
    print(f"[+] Aligned symbol definitions using {len(indent)} spaces at line {target_idx + 1}.")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(cleaned)

print("[+] Cleaned and realigned telegram_interactive.py.")
