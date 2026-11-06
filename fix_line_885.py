path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Convert tabs to 4 spaces across the entire file to kill tab/space mixing
lines = [l.replace("\t", "    ") for l in lines]

target_idx = 885 - 1  # 0-indexed line 885
if 0 <= target_idx < len(lines):
    prev_line = lines[target_idx - 1]
    curr_line = lines[target_idx]
    
    prev_ws = prev_line[:len(prev_line) - len(prev_line.lstrip(" "))]
    curr_stripped = curr_line.lstrip(" ")
    
    # If the previous line did not end with a colon (:), line 885 must have identical indentation
    if not prev_line.strip().endswith(":"):
        lines[target_idx] = prev_ws + curr_stripped
        print(f"[+] Re-aligned line 885 to {len(prev_ws)} spaces matching line 884.")
    else:
        # If previous line had a colon, line 885 should be exactly +4 spaces
        lines[target_idx] = prev_ws + "    " + curr_stripped
        print(f"[+] Indented line 885 to {len(prev_ws) + 4} spaces following block opener.")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Cleaned whitespace and adjusted line 885.")
