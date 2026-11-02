path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Inspect enclosing function definition
target_idx = -1
for i, line in enumerate(lines):
    if 'direction = top["direction"]' in line or "direction = top['direction']" in line:
        target_idx = i
        break

if target_idx != -1:
    print(f"[*] Found target statement at line {target_idx + 1}")
    
    # Trace backwards to find the def or enclosing loop/if
    enclosing_indent = ""
    for b in range(target_idx - 1, max(0, target_idx - 30), -1):
        stripped = lines[b].strip()
        if stripped.startswith(("def ", "async def ", "for ", "while ")):
            func_base = len(lines[b]) - len(lines[b].lstrip())
            enclosing_indent = " " * (func_base + 4)
            break
        elif stripped and not stripped.startswith(("#", '"""', "'''")):
            # If standard line preceding the lock/direction logic
            line_indent = len(lines[b]) - len(lines[b].lstrip())
            if line_indent > 0:
                enclosing_indent = " " * line_indent
                break

    if not enclosing_indent:
        enclosing_indent = "    "

    print(f"[*] Applying indentation: {repr(enclosing_indent)}")
    
    # Re-align direction block starting at target_idx
    for k in range(target_idx, min(len(lines), target_idx + 10)):
        st = lines[k].strip()
        if st and any(kwd in st for kwd in ['direction =', 'lots =', 'sl =', 'tp =', 'deviation =', 'request =']):
            lines[k] = enclosing_indent + st + "\n"
            print(f"    Aligned line {k + 1}: {lines[k].strip()}")
else:
    print("[-] Statement 'direction = top[\"direction\"]' not found.")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Re-alignment complete.")
