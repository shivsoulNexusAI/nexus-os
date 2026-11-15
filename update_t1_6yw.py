import json
from pathlib import Path

config_path = Path(r"C:\Quant-Nexus-Eng\t1_telegram_config.json")

if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    
    # Locate or request the full token ending in 6YW
    # Let's inspect what's currently there or inject the correct structure
    print(f"[INFO] Current t1 config keys: {list(data.keys())}")
    
    # If you have the full token, replace the placeholder below. 
    # For now, let's look for any key that holds the token and make sure it ends with 6YW or update it.
    # We will update both the empty key '' and 'token' / 'bot_token' if present.
    
    # If you want to input the exact full token, replace the string below:
    # target_token = "YOUR_FULL_TOKEN_ENDING_IN_6YW"
    
    print("[SUCCESS] t1_telegram_config.json path verified.")
else:
    print("[ERROR] t1_telegram_config.json not found!")
