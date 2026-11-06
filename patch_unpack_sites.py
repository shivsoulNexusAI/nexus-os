import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

lines = text.splitlines(keepends=True)
patched = 0

for i, line in enumerate(lines):
    # Match both scan handler and instant-trigger locations
    if "Executing full universe evaluation" in line or "[INSTANT-TRIGGER]" in line:
        print(f"[*] Found target region at line {i+1}: {line.strip()}")
        # Inspect following 8 lines for a 2-variable unpack: a, b = func(...)
        for j in range(i + 1, min(len(lines), i + 10)):
            m = re.match(r"^(\s+)(\w+)\s*,\s*(\w+)\s*=\s*(.+)$", lines[j])
            if m:
                indent, v1, v2, expr = m.groups()
                # Skip if already wrapped with safe logic
                if "_safe_res" in expr:
                    continue
                print(f"    Patching unpack at line {j+1}: {v1}, {v2} = {expr}")
                lines[j] = (
                    f"{indent}_safe_res = {expr}\n"
                    f"{indent}{v1}, {v2} = (_safe_res[0], _safe_res[1]) if isinstance(_safe_res, (list, tuple)) and len(_safe_res) >= 2 else (str(_safe_res or ''), None)\n"
                )
                patched += 1

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"[+] Total unpack sites safeguarded: {patched}")
