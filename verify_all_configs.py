import json
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
configs = ["t1_telegram_config.json", "t2_telegram_config.json", "master_telegram_trio.json", "accounts.json"]

print("==================================================")
print("     QuantNexus Configuration Integrity Check     ")
print("==================================================")

for cfg_name in configs:
    cfg_path = BASE_DIR / cfg_name
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            print(f"\n[OK] {cfg_name}:")
            # Mask tokens for safe printing while showing identity
            for k, v in data.items():
                if isinstance(v, str) and len(v) > 10:
                    masked = v[:6] + "..." + v[-4:] if len(v) > 10 else v
                    print(f"    - {k}: {masked}")
                else:
                    print(f"    - {k}: {v}")
        except Exception as e:
            print(f"\n[ERROR] Failed to parse {cfg_name}: {e}")
    else:
        print(f"\n[INFO] Optional/Missing file: {cfg_name}")

print("\n==================================================")
