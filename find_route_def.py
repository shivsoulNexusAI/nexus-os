from pathlib import Path
import re

found = False
for file in Path("C:/Quant-Nexus-Eng").glob("*.py"):
    try:
        text = file.read_text(encoding="utf-8", errors="ignore")
        if "def route_silver_bullet_order" in text:
            print(f"[+] Found route_silver_bullet_order in: {file.name}")
            lines = text.splitlines()
            for idx, l in enumerate(lines):
                if "def route_silver_bullet_order" in l:
                    for i in range(idx, min(len(lines), idx + 40)):
                        print(f"  {i+1:3d}: {lines[i]}")
                    found = True
                    break
    except Exception:
        pass

if not found:
    print("[-] route_silver_bullet_order not defined locally in C:\\Quant-Nexus-Eng")