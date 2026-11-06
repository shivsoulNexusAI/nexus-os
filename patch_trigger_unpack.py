import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Pattern 1: Find where daemon error is caught and printed
# Usually: except Exception as e: print(f"[!] Daemon error: {e}")
# We ensure the trigger execution inside that try block handles tuples safely.

# Replace bare unpack assignments like: msg, markup = func(...) or a, b = execute(...)
# with safe unpacking:
def make_safe_unpack(match):
    full = match.group(0)
    var1 = match.group(1)
    var2 = match.group(2)
    expr = match.group(3)
    indent = match.group(4)
    return f"{indent}_res = {expr}\n{indent}{var1}, {var2} = (_res if isinstance(_res, (list, tuple)) and len(_res) >= 2 else (str(_res), None))"

# Search for two-variable assignments right after INSTANT-TRIGGER
lines = text.splitlines(keepends=True)
for i, line in enumerate(lines):
    if "INSTANT-TRIGGER" in line:
        for j in range(i, min(len(lines), i + 15)):
            # Check for pattern: var1, var2 = some_call(...)
            m = re.match(r"^(\s+)(\w+)\s*,\s*(\w+)\s*=\s*(.+)$", lines[j])
            if m:
                indent, v1, v2, expr = m.groups()
                print(f"[*] Found unpack at line {j+1}: {v1}, {v2} = {expr}")
                lines[j] = f"{indent}_res = {expr}\n{indent}{v1}, {v2} = (_res[0], _res[1]) if isinstance(_res, (list, tuple)) and len(_res) >= 2 else (str(_res) if _res else '', None)\n"

text = "".join(lines)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Successfully made daemon trigger unpack safe.")
