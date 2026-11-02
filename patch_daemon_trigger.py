import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Scan lines around INSTANT-TRIGGER to fix any empty returns and unpack assignments
modified = False
for i, line in enumerate(lines):
    if "INSTANT-TRIGGER" in line:
        print(f"[*] Found INSTANT-TRIGGER at line {i+1}")
        # Look ahead up to 25 lines to find returns and fix unpack statements
        for j in range(i, min(len(lines), i + 30)):
            # Fix bare return
            if lines[j].strip() == "return":
                base_sp = " " * (len(lines[j]) - len(lines[j].lstrip()))
                lines[j] = base_sp + 'return "Trigger completed", None\n'
                print(f"    Fixed bare return at line {j+1}")
                modified = True
            elif lines[j].strip().startswith("return ") and "," not in lines[j]:
                base_sp = " " * (len(lines[j]) - len(lines[j].lstrip()))
                ret_val = lines[j].strip()[7:]
                lines[j] = base_sp + f'return {ret_val}, None\n'
                print(f"    Converted single return to 2-tuple at line {j+1}")
                modified = True

# Also ensure the daemon sleep interval is strictly 60 seconds
content = "".join(lines)
content = re.sub(r'asyncio\.sleep\([1-9]\)', 'asyncio.sleep(60)', content)
content = re.sub(r'time\.sleep\([1-9]\)', 'time.sleep(60)', content)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("[+] Successfully patched daemon trigger return values and 60s cadence.")
