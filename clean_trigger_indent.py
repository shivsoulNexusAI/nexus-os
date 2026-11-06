path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# 1. Strip all recent patches that introduced loose sym or cooldown lines
scrubbed = []
for line in lines:
    if any(marker in line for marker in [
        "# Safe symbol resolution guard",
        "locals().get('target_symbol')",
        "isinstance(candidate, dict)",
        "EXECUTION_COOLDOWN_MAP = {}",
        "EXECUTION_COOLDOWN_MAP",
        "COOLDOWN_SECONDS",
        "_target = symbol",
        "sym = locals().get"
    ]):
        continue
    scrubbed.append(line)

# 2. Locate the loop where [INSTANT-TRIGGER] prints
# Find the exact loop variable name
reconstructed = []
for idx, line in enumerate(scrubbed):
    if "[INSTANT-TRIGGER]" in line:
        # Detect exact indentation of the log line
        leading_ws = line[:len(line) - len(line.lstrip(" "))]
        # Insert a clean definition using the exact same indentation right above the print/trigger
        clean_def = (
            f"{leading_ws}sym = None\n"
            f"{leading_ws}for _var in ['symbol', 'target_symbol', 'pair', 'asset', 'cand', 'candidate']:\n"
            f"{leading_ws}    if _var in locals():\n"
            f"{leading_ws}        _val = locals()[_var]\n"
            f"{leading_ws}        sym = _val if isinstance(_val, str) else (getattr(_val, 'symbol', None) or (_val.get('symbol') if isinstance(_val, dict) else None))\n"
            f"{leading_ws}        if sym: break\n"
        )
        reconstructed.append(clean_def)
    reconstructed.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(reconstructed)

print("[+] Cleaned and unified trigger block.")
