import json

# Put your fresh token between the quotes below
NEW_TOKEN = "8578781048:AAHCDrhqtH6gwcm1R3YZvNIu9zvAPM5Y5xU"

# 1. Update config_10k.json
cfg_path = r"C:\Quant-Nexus-Eng\gemini-to-king-gifted\Config\config_10k.json"
try:
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
except Exception:
    cfg = {}

cfg["bot_token"] = NEW_TOKEN
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)

# 2. Patch sovereign_10k.py lines
py_path = r"C:\Quant-Nexus-Eng\gemini-to-king-gifted\sovereign_10k.py"
with open(py_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip().startswith('BOT_TOKEN = "') or line.strip().startswith('"bot_token": "8578781048:'):
        if line.strip().startswith('BOT_TOKEN = "'):
            new_lines.append(f'BOT_TOKEN = "{NEW_TOKEN}"\n')
        else:
            new_lines.append(f'    "bot_token": "{NEW_TOKEN}",\n')
    else:
        new_lines.append(line)

with open(py_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("SUCCESS: Token updated cleanly in both files.")