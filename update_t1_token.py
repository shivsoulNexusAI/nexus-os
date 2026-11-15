import json
from pathlib import Path

config_path = Path(r"C:\Quant-Nexus-Eng\t1_telegram_config.json")

if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    
    # Replace this placeholder string with your actual Quant Alert Bot token from BotFather
    quant_alert_token = "YOUR_QUANT_ALERT_BOT_TOKEN_HERE"
    
    data["bot_name"] = "Quant Alert Bot"
    # Update both possible key formats where the token might be stored
    if "" in data:
        data[""] = quant_alert_token
    if "token" in data:
        data["token"] = quant_alert_token
    if "bot_token" in data:
        data["bot_token"] = quant_alert_token

    config_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print("[SUCCESS] Updated t1_telegram_config.json with Quant Alert Bot token structure.")
else:
    print("[ERROR] t1_telegram_config.json not found!")
