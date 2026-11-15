import os
import re
from pathlib import Path
import httpx

search_dirs = [
    Path("C:/Quant-Nexus-Eng"),
    Path("C:/Quant-Nexus-Prod")
]

found_token = None
print("=" * 85)
print("SCANNING FOR NEXUS GOLD 24/7 TELEGRAM TOKEN (SUFFIX: _A5I)")
print("=" * 85)

# 1. Search code and config files for token pattern ending in _A5I
for root_dir in search_dirs:
    if not root_dir.exists():
        continue
    for ext in ["*.py", "*.env", "*.txt", "*.json", "*.cfg"]:
        for p in root_dir.rglob(ext):
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                tokens = re.findall(r"(\d{8,11}:[A-Za-z0-9_-]{30,45})", content)
                for t in tokens:
                    if t.endswith("_A5I") or "_A5I" in t:
                        found_token = t
                        print(f"[+] Found candidate token in: {p}")
                        break
                if found_token:
                    break
            except Exception:
                pass
        if found_token:
            break

if found_token:
    print(f"[+] Token Located: {found_token[:10]}...{found_token[-5:]}")
    try:
        r = httpx.get(f"https://api.telegram.org/bot{found_token}/getMe", timeout=6.0)
        if r.status_code == 200:
            bot_info = r.json().get("result", {})
            name = bot_info.get("first_name", "")
            username = bot_info.get("username", "")
            b_id = bot_info.get("id")
            print(f"[+] Telegram API Handshake SUCCESSFUL:")
            print(f"    Bot Name : {name}")
            print(f"    Username : @{username}")
            print(f"    Bot ID   : {b_id}")

            gold_cfg = f"""# -*- coding: utf-8 -*-
# TELEGRAM ROUTING: NEXUS GOLD 24/7 (@{username}) FOR ACCOUNT #278062042
TELEGRAM_BOT_TOKEN = "{found_token}"
TELEGRAM_CHAT_ID = "5279761713"
TARGET_ACCOUNT = 278062042
"""
            out_file = Path("C:/Quant-Nexus-Eng/telegram_gold_config.py")
            out_file.write_text(gold_cfg, encoding="utf-8")
            print(f"[+] Successfully wrote {out_file}")

            # Transmit Handshake Card
            ping_url = f"https://api.telegram.org/bot{found_token}/sendMessage"
            payload = {
                "chat_id": "5279761713",
                "text": (
                    f"🥇 <b>[NEXUS GOLD 24/7 PIPELINE ONLINE]</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"<b>Bot:</b> {name} (@{username})\n"
                    f"<b>Dedicated Target:</b> Account #278062042 (HFT Vision)\n"
                    f"<b>Status:</b> Handshake Confirmed\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ Gold HFT Straddle telemetry isolated."
                ),
                "parse_mode": "HTML"
            }
            res = httpx.post(ping_url, json=payload, timeout=10.0)
            if res.status_code == 200:
                print(f"[SUCCESS] Handshake notification delivered to @{username} on your phone!")
            else:
                print(f"[-] Telegram dispatch error ({res.status_code}): {res.text}")
        else:
            print(f"[-] Telegram API returned HTTP {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[-] Handshake network error: {e}")
else:
    print("[-] Token ending with '_A5I' not detected in C:/Quant-Nexus-Eng or C:/Quant-Nexus-Prod.")
    print("[*] If this bot was created recently in @BotFather, reply with the prefix of the token string to bind it directly.")
print("=" * 85)