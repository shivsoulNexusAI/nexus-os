# -*- coding: utf-8 -*-
import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# -------------------------------------------------------------
# 1. Clean Mojibake and Corrupted Emoji Literals
# -------------------------------------------------------------
mojibake_replacements = {
    "вЉЄ": "⚪",
    "рџЋЇ": "🎯",
    "рџ’j": "💼",
    "рџ’": "💼",
    "рџ›ЎпёЏ": "🛡️",
    "рџ›Ў": "🛡️",
    "вЏ±пёЏ": "⏱️",
    "вЏ±": "⏱️",
    "рџЏ№": "🏹",
    "рџџў": "🟢",
    "рџ”ґ": "🔴",
    "рџ”„": "🔄",
    "рџЏ›пёЏ": "🏛️",
    "рџЏ›": "🏛️",
    "рџ§і": "🧮",
}

for bad, good in mojibake_replacements.items():
    text = text.replace(bad, good)

# -------------------------------------------------------------
# 2. Fix Double Parentheses: ((50%)) -> (50%)
# -------------------------------------------------------------
text = re.sub(r'\(\((\d+%?)\)\)', r'(\1)', text)

# -------------------------------------------------------------
# 3. Ensure parse_mode="HTML" across Telegram sends/edits
# -------------------------------------------------------------
def inject_parse_mode(match):
    call = match.group(0)
    if 'parse_mode' not in call:
        return call[:-1] + ', parse_mode="HTML")'
    return call

# Target send_message and edit_message_text calls
text = re.sub(r'send_message\([^)]+\)', inject_parse_mode, text)
text = re.sub(r'edit_message_text\([^)]+\)', inject_parse_mode, text)

# -------------------------------------------------------------
# 4. Standardize Scan Loop Interval to 60 Seconds
# -------------------------------------------------------------
# Look for the sleep statement in the background daemon loop
text = re.sub(r'await asyncio\.sleep\(15\)', 'await asyncio.sleep(60)', text)
text = re.sub(r'\[15s-SCAN ALL 5\]', '[60s-SCAN ALL 5]', text)
text = re.sub(r'Autonomous 15s scan', 'Autonomous 60s scan', text)

# -------------------------------------------------------------
# 5. High-Probability Trigger Guard (>= 75% Edge, Locked Check)
# -------------------------------------------------------------
# Ensure the trigger block handles high probability setups correctly
trigger_block = """                if cleared and not is_locked:
                    sym = candidate.get("symbol") if isinstance(candidate, dict) else getattr(candidate, "symbol", None)
                    edge_val = candidate.get("edge", 0) if isinstance(candidate, dict) else getattr(candidate, "edge", 0)
                    if not sym or edge_val < 75:
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
                    print(f"[{t_now}] [INSTANT-TRIGGER] Firing {direction} on {sym} ({lots}L @ {edge_val}% Edge)...")

                    ok, res_msg, ticket = await asyncio.to_thread(execute_market_order, sym, direction, lot=lots, sl=sl, tp=tp)
                    if ok:"""

# Safe splice of the trigger block
pattern = r'([ \t]*)if cleared and not is_locked:.*?(?=[ \t]*if ok:)'
if re.search(pattern, text, re.DOTALL):
    text = re.sub(pattern, trigger_block + "\n", text, count=1, flags=re.DOTALL)
    text = re.sub(r'if ok:\s*if ok:', 'if ok:', text)
    print("[+] Trigger block calibrated to 60s / >= 75% edge guard.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Final Telegram message & loop audit applied.")
