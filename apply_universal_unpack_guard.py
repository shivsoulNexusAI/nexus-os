import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# Helper function to inject if missing
guard_func = """
def _guard_2tuple(val):
    if isinstance(val, (tuple, list)):
        if len(val) >= 2:
            return val[0], val[1]
        elif len(val) == 1:
            return val[0], None
        return "", None
    if isinstance(val, str):
        return val, None
    return "", None
"""

if "_guard_2tuple" not in code:
    code = guard_func + "\n" + code

lines = code.splitlines(keepends=True)
patched_count = 0

for i, line in enumerate(lines):
    # Match both scan handler and instant-trigger locations
    if "Executing full universe evaluation" in line or "[INSTANT-TRIGGER]" in line:
        for j in range(i + 1, min(len(lines), i + 15)):
            # Look for 2-variable assignment: a, b = func(...)
            m = re.match(r"^(\s+)(\w+)\s*,\s*(\w+)\s*=\s*(.+)$", lines[j])
            if m:
                indent, v1, v2, expr = m.groups()
                if "_guard_2tuple" not in expr:
                    lines[j] = f"{indent}{v1}, {v2} = _guard_2tuple({expr})\n"
                    print(f"[+] Protected unpack at line {j+1}: {v1}, {v2} = _guard_2tuple({expr})")
                    patched_count += 1

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"[+] Total unpack sites wrapped with _guard_2tuple: {patched_count}")
