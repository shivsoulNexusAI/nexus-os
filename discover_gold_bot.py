import os
import re
from pathlib import Path
import httpx

search_dirs = [Path(r"C:\Quant-Nexus-Eng"), Path(r"C:\Quant-Nexus-Prod")]
candidate_tokens = set()

for d in search_dirs:
    if not d.exists(): continue
    for p in d.rglob("*.py"):
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            # Collect tokens
            matches = re.findall(r"(\d{8,11}:[A-Za-z0-9_-]{35})", content)
            for m in matches:
                candidate_tokens.add(m)
        except Exception:
            pass

print("=" * 85)
print("AUDITING TELEGRAM BOT ROSTER FOR NEXUS GOLD 24/7 (@nexus_gold247)")
print("=" * 85)

gold_token = None
for tok in candidate_tokens:
    try:
        r = httpx.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=6.0)
        if r.status_code == 200:
            data = r.json().get("result", {})
            b_name = data.get("first_name", "")
            b_user = data.get("username", "")
            b_id = data.get("id")
            print(f"Token: {tok[:10]}...{tok[-5:]} | Name: {b_name} | @{b_user} (ID: {b_id})")
            if "gold" in b_user.lower() or "gold" in b_name.lower():
                gold_token = tok
                print(f"  ==> [MATCH CONFIRMED FOR NEXUS GOLD 24/7] <==\n")
    except Exception:
        pass

if not gold_token:
    print("\n[-] @nexus_gold247 token not found in existing files.")
    print("[*] Please provide the bot token for @nexus_gold247 to bind it to #278062042.")
else:
    # Save isolated config for Gold
    cfg = f"""# -*- coding: utf-8 -*-
TELEGRAM_BOT_TOKEN = "{gold_token}"
TELEGRAM_CHAT_ID = "5279761713"
TARGET_LOGIN = 278062042
"""
    Path(r"C:\Quant-Nexus-Eng\telegram_gold_config.py").write_text(cfg, encoding="utf-8")
    print(f"[+] Saved C:\\Quant-Nexus-Eng\\telegram_gold_config.py successfully.")
print("=" * 85)