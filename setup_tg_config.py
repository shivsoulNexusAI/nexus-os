import re
from pathlib import Path

bridge_path = Path(r"C:\Quant-Nexus-Eng\nexus_telegram_bridge.py")
text = bridge_path.read_text(encoding="utf-8", errors="ignore")

tok_match = re.search(r"(\d{8,11}:[A-Za-z0-9_-]{35})", text)
chat_match = re.search(r"chat_id\s*=\s*['\"]?(-?\d+)['\"]?", text, re.IGNORECASE)

if not tok_match:
    print("[-] Failed to find token in bridge file.")
    exit(1)

token = tok_match.group(1)
chat_id = chat_match.group(1) if chat_match else "5279761713"

config_content = f"""# -*- coding: utf-8 -*-
TELEGRAM_BOT_TOKEN = "{token}"
TELEGRAM_CHAT_ID = "{chat_id}"
"""

out_path = Path(r"C:\Quant-Nexus-Eng\telegram_config.py")
out_path.write_text(config_content, encoding="utf-8")
print(f"[+] Centralized telegram_config.py created successfully.")
print(f"    Token: {token[:6]}...{token[-4:]} | Chat ID: {chat_id}")