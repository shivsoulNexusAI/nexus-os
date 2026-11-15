import json
from pathlib import Path

CFG_FILE = Path(r"C:\Quant-Nexus-Eng\nexus_straddle_matrix.json")
with open(CFG_FILE, "r", encoding="utf-8") as f:
    cfg = json.load(f)

# Calibrate BTCUSD bracket dimensions to account for $74k price level
if "BTCUSD" in cfg["asset_matrix"]:
    cfg["asset_matrix"]["BTCUSD"]["buffer_points"] = 1800
    cfg["asset_matrix"]["BTCUSD"]["sl_points"] = 1200
    cfg["asset_matrix"]["BTCUSD"]["be_tier1_points"] = 1200
    cfg["asset_matrix"]["BTCUSD"]["be_tier2_points"] = 2400

with open(CFG_FILE, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)

print("[+] Calibrated BTCUSD bracket geometry in nexus_straddle_matrix.json")