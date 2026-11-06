path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Replace any broken top opportunity format line with safe unpacking
old_target = 'lines.append(f"рџЋЇ TOP OPPORTUNITY: {sym} ({direction} @ {edge}%)")'
alt_target = 'lines.append(f"🎯 TOP OPPORTUNITY: {sym} ({direction} @ {edge}%)")'

safe_block = """        if scans:
            top_s = scans[0]
            top_sym = top_s.get('symbol', 'N/A') if isinstance(top_s, dict) else getattr(top_s, 'symbol', 'N/A')
            top_dir = top_s.get('direction', 'BUY') if isinstance(top_s, dict) else getattr(top_s, 'direction', 'BUY')
            top_edge = top_s.get('edge', 0) if isinstance(top_s, dict) else getattr(top_s, 'edge', 0)
            lines.append(f"🎯 TOP OPPORTUNITY: {top_sym} ({top_dir} @ {top_edge}%)")"""

if old_target in text:
    text = text.replace(old_target, safe_block, 1)
    print("[+] Replaced broken target line with safe unpacked opportunity block.")
elif alt_target in text:
    text = text.replace(alt_target, safe_block, 1)
    print("[+] Replaced alt target line with safe unpacked opportunity block.")
else:
    # Generic regex substitution for lines.append(...TOP OPPORTUNITY...)
    import re
    text = re.sub(
        r'([ \t]*)lines\.append\(f["\'].*?TOP OPPORTUNITY.*?\)',
        safe_block,
        text,
        count=1
    )
    print("[+] Applied regex patch to render_leaderboard_card.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] render_leaderboard_card patch complete.")
