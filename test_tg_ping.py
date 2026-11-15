import asyncio
import os

# Check standard token files or script variables
for path in [r"C:\Quant-Nexus-Eng\telegram_config.py", r"C:\Quant-Nexus-Prod\core\telegram_alert.py", r"C:\Quant-Nexus-Eng\weekly_alpha_reporter.py"]:
    if os.path.exists(path):
        print(f"[+] Found config module: {path}")

# Execute quick ping using python-telegram-bot / httpx
try:
    import httpx
    print("[+] httpx networking library available for low-latency dispatch.")
except ImportError:
    print("[!] httpx not installed.")