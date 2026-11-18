import json
from pathlib import Path

config_path = Path(r"C:\Quant-Nexus-Eng\t1_telegram_config.json")

if config_path.exists():
    # Load existing content
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    
    # Set correct Quant Alert Bot token
    quant_token = "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw"
    
    data["bot_name"] = "Quant Alert Bot"
    data[""] = quant_token      # Matches your schema's empty string key
    data["token"] = quant_token  # Standard fallback key
    
    # Save clean JSON
    config_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print("[SUCCESS] t1_telegram_config.json successfully re-written with Quant Alert Bot token!")
else:
    print("[ERROR] t1_telegram_config.json not found!")
