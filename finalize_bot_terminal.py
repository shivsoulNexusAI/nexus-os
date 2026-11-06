import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# 1. Clean buttons & characters
text = text.replace("рџ’j", "💼").replace("рџ”„", "🔄").replace("вљ€", "⚪")
text = re.sub(r'InlineKeyboardButton\s*\(\s*text\s*=\s*["\'].*?Accounts Switchboard["\']', 'InlineKeyboardButton(text="💼 Accounts Switchboard"', text)
text = re.sub(r'InlineKeyboardButton\s*\(\s*text\s*=\s*["\'].*?Run Scan Again["\']', 'InlineKeyboardButton(text="🔄 Run Scan Again"', text)

# 2. Ensure mt5.initialize() attaches cleanly to active GUI terminal
text = re.sub(r'mt5\.initialize\(.*?\)', 'mt5.initialize()', text)

# 3. Rebuild the trigger loop cleanly between "if cleared and not is_locked:" and "if ok:"
clean_trigger = """                if cleared and not is_locked:
                    sym = candidate.get("symbol")
                    if not sym:
                        continue

                    if "EXEC_COOLDOWNS" not in globals():
                        globals()["EXEC_COOLDOWNS"] = {}
                    import time as _t_mod
                    _now_s = _t_mod.time()
                    if sym in globals()["EXEC_COOLDOWNS"] and (_now_s - globals()["EXEC_COOLDOWNS"][sym]) < 300:
                        continue

                    lots = candidate.get("calculated_lots", 0.01)
                    sl = candidate.get("sl", 0.0)
                    tp = candidate.get("tp", 0.0)

                    globals()["EXEC_COOLDOWNS"][sym] = _now_s
                    print(f"[{t_now}] [INSTANT-TRIGGER] Firing {direction} on {sym} ({lots}L @ {edge}% Edge)...")

                    ok, res_msg, ticket = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)

                    if ok:"""

# Regex replacement across the whole block
pattern = r'([ \t]*)if cleared and not is_locked:.*?(?=[ \t]*if ok:)'
if re.search(pattern, text, re.DOTALL):
    text = re.sub(pattern, clean_trigger, text, count=1, flags=re.DOTALL)
    print("[+] Trigger block replaced with clean 20/24 indentation.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Patch saved successfully.")
