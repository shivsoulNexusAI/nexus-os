import os
import shutil
import zipfile
from datetime import datetime, timezone
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
ENG_DIR = r"C:\Quant-Nexus-Eng"
BACKUP_DIR = r"C:\Quant-Nexus-Eng\backups"

os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
zip_path = os.path.join(BACKUP_DIR, f"Nexus_Engine_Checkpoint_{ts}.zip")

# Key files to preserve
TARGET_FILES = [
    "nexus_multi_straddle_daemon.py",
    "breakeven_engine.py",
    "ml_feature_pipeline.py",
    "train_regime_model_v2.py",
    "regime_classifier.pkl",
    "audit_runners_now.py",
    "audit_fleet_live.py",
    "audit_telemetry_summary.py",
    "audit_deal_exit.py",
    "nexus_multi_straddle.log"
]

print("=" * 80)
print(f"       QUANT-NEXUS CHECKPOINT & ARCHIVE CREATION [{ts} UTC]")
print("=" * 80)

# 1. Capture Live Account Telemetry
telemetry_txt = []
if mt5.initialize(path=TERMINAL, portable=False):
    acc = mt5.account_info()
    positions = mt5.positions_get() or []
    orders = mt5.orders_get() or []
    telemetry_txt.append(f"Account: {acc.login} | Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f}")
    telemetry_txt.append(f"Active Positions: {len(positions)} | Pending Orders: {len(orders)}\n")
    for p in positions:
        telemetry_txt.append(f"POS #{p.ticket} {p.symbol} {'BUY' if p.type==0 else 'SELL'} {p.volume:.2f}L | Entry: {p.price_open} | SL: {p.sl} | PnL: ${p.profit:+.2f}")
    for o in orders:
        telemetry_txt.append(f"ORD #{o.ticket} {o.symbol} Type:{o.type} {o.volume_current:.2f}L | Price: {o.price_open} | SL: {o.sl} | TP: {o.tp}")
    mt5.shutdown()

snap_file = os.path.join(ENG_DIR, "checkpoint_state.txt")
with open(snap_file, "w", encoding="utf-8") as f:
    f.write("\n".join(telemetry_txt))

# 2. Package Zip
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
    for fname in TARGET_FILES:
        fpath = os.path.join(ENG_DIR, fname)
        if os.path.exists(fpath):
            zipf.write(fpath, arcname=fname)
            print(f"[+] Archived: {fname}")
    if os.path.exists(snap_file):
        zipf.write(snap_file, arcname="checkpoint_state.txt")
        print("[+] Archived: checkpoint_state.txt")

size_mb = os.path.getsize(zip_path) / (1024 * 1024)
print("-" * 80)
print(f"[SUCCESS] Checkpoint saved: {zip_path} ({size_mb:.2f} MB)")
print("=" * 80)