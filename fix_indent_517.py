path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Target the entire block from the separator line down to the SL/TP line
old_block = """    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

             if scans:
             top_s = scans[0]
             top_sym = top_s.get('symbol', 'N/A') if isinstance(top_s, dict) else getattr(top_s, 'symbol', 'N/A')
             top_dir = top_s.get('direction', 'BUY') if isinstance(top_s, dict) else getattr(top_s, 'direction', 'BUY')
             top_edge = top_s.get('edge', 0) if isinstance(top_s, dict) else getattr(top_s, 'edge', 0)
             lines.append(f"🎯 TOP OPPORTUNITY: {top_sym} ({top_dir} @ {top_edge}%)")

    lines.append(f" • Entry: ${top.get('price')}")

    lines.append(f" • SL: ${top.get('sl')} | TP: ${top.get('tp')}")"""

new_block = """    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    if scans:
        top = scans[0] if isinstance(scans[0], dict) else {}
        top_sym = top.get('symbol', 'N/A')
        top_dir = top.get('direction', 'BUY')
        top_edge = top.get('edge', 0)
        lines.append(f"🎯 TOP OPPORTUNITY: {top_sym} ({top_dir} @ {top_edge}%)")
        lines.append(f" • Entry: ${top.get('price', 0.0)}")
        lines.append(f" • SL: ${top.get('sl', 0.0)} | TP: ${top.get('tp', 0.0)}")"""

# Perform replacement
if old_block in text:
    text = text.replace(old_block, new_block, 1)
    print("[+] Replaced exact block successfully.")
else:
    # Robust line-by-line surgical replacement
    lines = text.splitlines(keepends=True)
    idx_sep = -1
    for i, l in enumerate(lines):
        if 'lines.append("━━━━━━━━━━━━━━━━━━━━━━")' in l and i > 500:
            idx_sep = i
            break
    if idx_sep != -1:
        # Look ahead for the SL | TP line
        idx_end = -1
        for j in range(idx_sep, min(len(lines), idx_sep + 20)):
            if " • SL:" in lines[j] and "TP:" in lines[j]:
                idx_end = j
                break
        if idx_end != -1:
            replacement_lines = [l + "\n" for l in new_block.splitlines()]
            lines = lines[:idx_sep] + replacement_lines + lines[idx_end + 1:]
            text = "".join(lines)
            print(f"[+] Replaced lines {idx_sep+1} to {idx_end+1} with clean 4/8-space block.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] File saved.")
