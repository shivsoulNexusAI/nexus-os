import json
from pathlib import Path

config_path = Path(r"C:\Quant-Nexus-Eng\t1_telegram_config.json")

if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    # Update bot name metadata explicitly to Quant Alert Bot
    data["bot_name"] = "Quant Alert Bot"
    
    # Save back cleanly with standard UTF-8
    config_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print("[SUCCESS] t1_telegram_config.json updated: Assigned to 'Quant Alert Bot'")
else:
    print("[ERROR] t1_telegram_config.json not found!")
