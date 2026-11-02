import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Locate the INSTANT-TRIGGER block and wrap the function call that assigns two variables
modified = False
for i, line in enumerate(lines):
    if "INSTANT-TRIGGER" in line:
        for j in range(i, min(len(lines), i + 15)):
            match = re.match(r"^(\s+)(\w+)\s*,\s*(\w+)\s*=\s*(.+)$", lines[j])
            if match:
                indent, var1, var2, expr = match.groups()
                if "_res_tuple" not in expr:
                    print(f"[*] Wrapping unpack at line {j+1}: {var1}, {var2} = {expr.strip()}")
                    lines[j] = (
                        f"{indent}_res_tuple = {expr.strip()}\n"
                        f"{indent}{var1}, {var2} = (_res_tuple if isinstance(_res_tuple, (tuple, list)) and len(_res_tuple) >= 2 else (str(_res_tuple or ''), None))\n"
                    )
                    modified = True

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"[+] Completed trigger unpack patch. Modified: {modified}")
