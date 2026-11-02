path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

bad_tokens = [
    "Safe symbol resolution guard",
    "locals().get('target_symbol')",
    "locals().get('symbol')",
    "isinstance(candidate, dict)",
    "EXECUTION_COOLDOWN_MAP",
    "COOLDOWN_SECONDS",
    "_target = symbol",
    "clean_def",
    "sym = None",
    "_var in ['symbol'",
    "attempted_cooldown",
]

cleaned = [l for l in lines if not any(t in l for t in bad_tokens)]

with open(path, "w", encoding="utf-8") as f:
    f.writelines(cleaned)

print(f"[+] Purged injected lines. File reduced from {len(lines)} to {len(cleaned)} lines.")
