path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Target line 738 specifically (0-based index around 735-745)
for i in range(700, min(len(lines), 760)):
    line = lines[i]
    if 'direction = top["direction"]' in line or "direction = top['direction']" in line:
        print(f"[*] Found target statement at line {i + 1}: {repr(line)}")
        
        # Check surrounding execution block indentation (inside execute/trigger function)
        # Function body standard is 4 spaces, or 8 spaces if inside an if/try block
        target_indent = "        "  # 8 spaces inside handler/loop block
        for b in range(i - 1, max(0, i - 15), -1):
            st = lines[b].strip()
            if st.startswith("if ") or st.startswith("try:"):
                target_indent = " " * (len(lines[b]) - len(lines[b].lstrip()) + 4)
                break
            elif st.startswith("def ") or st.startswith("async def "):
                target_indent = " " * (len(lines[b]) - len(lines[b].lstrip()) + 4)
                break
        
        print(f"[*] Aligning block from line {i + 1} with indentation: {repr(target_indent)}")
        for k in range(i, min(len(lines), i + 12)):
            st = lines[k].strip()
            if st and any(kwd in st for kwd in ['direction =', 'lots =', 'sl =', 'tp =', 'deviation =', 'request =', 'result =']):
                lines[k] = target_indent + st + "\n"
                print(f"    Line {k + 1}: {lines[k].strip()}")
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Completed target line 738 patch.")
