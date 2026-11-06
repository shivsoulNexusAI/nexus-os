import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# 1. Lock ensure_mt5() to account 278025377
ensure_code = """def ensure_mt5():
    if not mt5.terminal_info() or not mt5.account_info() or mt5.account_info().login != 278025377:
        term_p = r"C:\\Program Files\\MetaTrader 5\\terminal64.exe"
        if not mt5.initialize(path=term_p, login=278025377, password="H@ngkook3695", server="Exness-MT5Trial5", timeout=60000):
            return False
    return True
"""
if "def ensure_mt5():" in text:
    text = re.sub(r'def ensure_mt5\(\):.*?(?=\n\w|\Z)', ensure_code, text, count=1, flags=re.DOTALL)
    print("[+] ensure_mt5() bound to 278025377.")

# 2. Fix the trigger loop where 'sym' is missing
# Replace from 'if cleared and not is_locked:' down to 'if ok:'
clean_block = """                if cleared and not is_locked:
                    sym = candidate.get("symbol") if isinstance(candidate, dict) else getattr(candidate, "symbol", None)
                    if not sym:
                        continue

                    if "EXEC_COOLDOWNS" not in globals():
                        globals()["EXEC_COOLDOWNS"] = {}
                    import time as _t_mod
                    _now_s = _t_mod.time()
                    if sym in globals()["EXEC_COOLDOWNS"] and (_now_s - globals()["EXEC_COOLDOWNS"][sym]) < 300:
                        continue

                    lots = candidate.get("calculated_lots", 0.01) if isinstance(candidate, dict) else 0.01
                    sl = candidate.get("sl", 0.0) if isinstance(candidate, dict) else 0.0
                    tp = candidate.get("tp", 0.0) if isinstance(candidate, dict) else 0.0

                    globals()["EXEC_COOLDOWNS"][sym] = _now_s
                    print(f"[{t_now}] [INSTANT-TRIGGER] Firing {direction} on {sym} ({lots}L @ {edge}% Edge)...")

                    ok, res_msg, ticket = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)
                    if ok:"""

# Target the entire block between 'if cleared and not is_locked:' and the first 'if ok:'
pattern = r'([ \t]*)if cleared and not is_locked:.*?(?=[ \t]*if ok:)'
if re.search(pattern, text, re.DOTALL):
    text = re.sub(pattern, clean_block + "\n", text, count=1, flags=re.DOTALL)
    # Deduplicate any stray adjacent 'if ok:'
    text = re.sub(r'if ok:\s*if ok:', 'if ok:', text)
    print("[+] Repaired trigger loop and guaranteed 'sym' definition.")
else:
    print("[-] Trigger pattern not matched. Attempting secondary splice...")
    # Secondary approach: if sym is used in print [INSTANT-TRIGGER]
    text = re.sub(r'(\n\s*)(print\(f"\[\{t_now\}\] \[INSTANT-TRIGGER\] Firing)', r'\1sym = candidate.get("symbol")\1\2', text, count=1)
    print("[+] Injected sym fallback before print statement.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] File written.")
