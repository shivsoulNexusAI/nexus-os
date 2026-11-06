path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

old_block = """    else:

        positions = mt5.positions_get(symbol=sym)

        if positions and len(positions) > 0:

            lines.append(f"🛡️ POSITION LOCK: Active trade already running on {sym}.")

        else:

            lines.append("🛡️ POSITION LOCK: Zero active positions. Clear to fire.")"""

new_block = """    else:
        chk_sym = top.get("symbol") if (scans and isinstance(top, dict)) else None
        if chk_sym:
            positions = mt5.positions_get(symbol=chk_sym)
            if positions and len(positions) > 0:
                lines.append(f"🛡️ POSITION LOCK: Active trade already running on {chk_sym}.")
            else:
                lines.append("🛡️ POSITION LOCK: Zero active positions on target. Clear to fire.")
        else:
            all_pos = mt5.positions_get() or []
            if all_pos:
                running_syms = list({p.symbol for p in all_pos})
                lines.append(f"🛡️ POSITION LOCK: Active trades running on {running_syms}.")
            else:
                lines.append("🛡️ POSITION LOCK: Zero active positions. Clear to fire.")"""

# Try exact string replace first
import re
if "positions = mt5.positions_get(symbol=sym)" in text:
    # Pattern to capture from 'else:' down to 'Clear to fire."'
    pattern = r'([ \t]*)else:\s*positions\s*=\s*mt5\.positions_get\(symbol=sym\).*?lines\.append\(["\']🛡️ POSITION LOCK: Zero active positions\. Clear to fire\.["\']\)'
    if re.search(pattern, text, re.DOTALL):
        text = re.sub(pattern, new_block, text, count=1, flags=re.DOTALL)
        print("[+] Replaced position lock block with regex.")
    else:
        # Fallback direct replacement
        text = text.replace("positions = mt5.positions_get(symbol=sym)", "chk_sym = top.get('symbol') if (scans and isinstance(top, dict)) else None\n        positions = mt5.positions_get(symbol=chk_sym) if chk_sym else (mt5.positions_get() or [])")
        text = text.replace("{sym}", "{chk_sym}")
        print("[+] Applied fallback inline replacement.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] fix_render_lock.py completed.")
