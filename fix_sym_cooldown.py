import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Fix any loose references where sym was used without definition
# Common patterns in this block are "symbol" or "candidate['symbol']"
buggy_block = """            now_ts = time.time()
            if sym in EXECUTION_COOLDOWN_MAP and (now_ts - EXECUTION_COOLDOWN_MAP[sym]) < COOLDOWN_SECONDS:
                continue
            EXECUTION_COOLDOWN_MAP[sym] = now_ts"""

clean_block = """            # Institutional 5-minute cooldown per symbol
            _target = symbol if 'symbol' in locals() else (sym if 'sym' in locals() else candidate.get('symbol'))
            now_ts = time.time()
            if _target:
                if _target in EXECUTION_COOLDOWN_MAP and (now_ts - EXECUTION_COOLDOWN_MAP[_target]) < COOLDOWN_SECONDS:
                    continue
                EXECUTION_COOLDOWN_MAP[_target] = now_ts"""

if buggy_block in text:
    text = text.replace(buggy_block, clean_block, 1)
    print("[+] Replaced buggy sym check with universal _target identifier.")
else:
    # Generic regex replacement for any variant referencing EXECUTION_COOLDOWN_MAP[sym]
    text = re.sub(
        r"if\s+sym\s+in\s+EXECUTION_COOLDOWN_MAP.*?:.*?EXECUTION_COOLDOWN_MAP\[sym\]\s*=\s*now_ts",
        clean_block.strip(),
        text,
        flags=re.DOTALL
    )
    print("[+] Applied regex repair to EXECUTION_COOLDOWN_MAP.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] File saved successfully.")
