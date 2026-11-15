import os
import sys
import json
import httpx
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
print("==================================================")
print("  QuantNexus Fleet & Telemetry Dry-Run Check      ")
print("==================================================")

# 1. Check Directory and Core Files
print(f"[*] Inspecting workspace directory: {BASE_DIR}")
if not BASE_DIR.exists():
    print(f"[ERROR] Base directory {BASE_DIR} does not exist!")
    sys.exit(1)

required_configs = ["t1_telegram_config.json", "t2_telegram_config.json", "accounts.json"]
for cfg in required_configs:
    cfg_path = BASE_DIR / cfg
    if cfg_path.exists():
        print(f"  [OK] Found config: {cfg}")
    else:
        print(f"  [WARNING] Missing expected config: {cfg}")

# 2. Verify Telegram Dispatcher Connectivity
def verify_telegram():
    config_path = BASE_DIR / "t1_telegram_config.json"
    if not config_path.exists():
        print("[ERROR] t1_telegram_config.json not found for testing alerts.")
        return False
    
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        token = data.get("", data.get("token", data.get("bot_token")))
        chat_id = data.get("chat_id", data.get("authorized_chat_id"))
        
        if not token or not chat_id:
            print("[ERROR] Telegram token or chat ID is missing in t1_telegram_config.json")
            return False

        url = f"https://api.telegram.org/bot{token}/getMe"
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code == 200:
            bot_info = resp.json().get("result", {})
            print(f"  [OK] Telegram Bot Connected Successfully: @{bot_info.get('username')}")
            return True
        else:
            print(f"  [FAILED] Telegram API /getMe error: {resp.text}")
            return False
    except Exception as e:
        print(f"  [ERROR] Telegram validation exception: {e}")
        return False

print("\n[*] Verifying Telegram Bot API Token...")
tele_status = verify_telegram()

# 3. Check MetaTrader 5 Python Module Integration
print("\n[*] Checking MetaTrader 5 Python Module...")
try:
    import MetaTrader5 as mt5
    print("  [OK] MetaTrader5 module is installed.")
    if mt5.initialize():
        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()
        print(f"  [OK] MT5 Terminal Connected. Build: {terminal_info.build if terminal_info else 'Unknown'}")
        if account_info:
            print(f"  [OK] Active Account Login: {account_info.login} | Server: {account_info.server}")
        mt5.shutdown()
    else:
        print("  [WARNING] mt5.initialize() failed. Ensure MT5 terminal is running or logged in.")
except ImportError:
    print("  [WARNING] 'MetaTrader5' Python package not found in this environment (pip install MetaTrader5).")

print("\n==================================================")
print(f"  Telemetry Check Complete. Status: {'READY' if tele_status else 'CHECK WARNINGS'}")
print("==================================================")
