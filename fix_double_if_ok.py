path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

import re
# Collapse duplicate "if ok:" on the same line or adjacent lines
text = re.sub(r'if ok:\s*if ok:', 'if ok:', text)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Deduplicated 'if ok:' in telegram_interactive.py")
