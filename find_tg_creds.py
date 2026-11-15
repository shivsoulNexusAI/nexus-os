import os
import re
from pathlib import Path

search_dirs = [Path(r"C:\Quant-Nexus-Eng"), Path(r"C:\Quant-Nexus-Prod")]
found = []

for d in search_dirs:
    if not d.exists():
        continue
    for p in d.rglob("*.py"):
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            # Match standard bot token format: 123456789:ABC...
            tokens = re.findall(r"(\d{8,11}:[A-Za-z0-9_-]{35})", content)
            chats = re.findall(r"chat_id\s*=\s*['\"]?(-?\d+)['\"]?", content, re.IGNORECASE)
            if tokens:
                found.append((str(p), tokens[0], chats[0] if chats else "Not found in file"))
        except Exception:
            pass

print("=" * 80)
print("TELEGRAM CREDENTIAL DISCOVERY")
print("=" * 80)
if found:
    for fpath, tok, chat in found:
        print(f"File   : {fpath}")
        print(f"Token  : {tok[:6]}...{tok[-4:]}")
        print(f"Chat ID: {chat}")
        print("-" * 80)
else:
    print("[-] No hardcoded tokens matched in .py files. Checking environment variables or imports...")