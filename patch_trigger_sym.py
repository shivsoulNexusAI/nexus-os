path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

patched = False
for idx, line in enumerate(lines):
    # Locate where the trigger log or sym reference occurs
    if "[INSTANT-TRIGGER]" in line or "EXECUTION_COOLDOWN_MAP" in line:
        # Prepend a safe fallback definition of sym right before the block
        insert_code = [
            "            # Safe symbol resolution guard\n",
            "            sym = locals().get('sym') or locals().get('symbol') or locals().get('target_symbol')\n",
            "            if not sym and 'candidate' in locals() and isinstance(candidate, dict):\n",
            "                sym = candidate.get('symbol')\n",
            "            if not sym:\n",
            "                continue\n"
        ]
        # Insert prior to the first line referencing sym or cooldown
        target_idx = max(0, idx - 2)
        lines = lines[:target_idx] + insert_code + lines[target_idx:]
        patched = True
        print(f"[+] Injected safe symbol resolver at line {target_idx + 1}.")
        break

if patched:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("[+] telegram_interactive.py updated successfully.")
else:
    print("[!] Target trigger pattern not found.")
