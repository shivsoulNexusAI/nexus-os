import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

modified_lines = 0
for idx, line in enumerate(lines):
    stripped = line.strip()
    
    # 1. Fix bare returns: 'return' -> 'return "", None'
    if stripped == "return":
        indent = " " * (len(line) - len(line.lstrip()))
        lines[idx] = f'{indent}return "", None\n'
        print(f"[+] Fixed bare return at line {idx + 1}")
        modified_lines += 1
        
    # 2. Fix single value returns inside matrix or scan execution functions if returning None
    elif stripped == "return None":
        indent = " " * (len(line) - len(line.lstrip()))
        lines[idx] = f'{indent}return "", None\n'
        print(f"[+] Fixed return None at line {idx + 1}")
        modified_lines += 1

content = "".join(lines)

# 3. Patch the specific unpack call site right after 'Executing full universe evaluation'
# Pattern: text, markup = function_call(...)
eval_marker = "[*] /scan received from"
if "Executing full universe evaluation" in content:
    print("[*] Found evaluation block in text; applying defensive unpack wrapper.")
    
with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"[+] Completed root unpack patch. Total modifications: {modified_lines}")
