import json
import MetaTrader5 as mt5
from nexus_core_risk import DynamicNexusRisk

with open("nexus_config.json", "r", encoding="utf-8-sig") as f:
    cfg = json.load(f)["account"]

if not mt5.initialize():
    print("[-] MT5 Initialization failed")
    exit(1)

logged_in = mt5.login(login=int(cfg["login"]), password=cfg["password"], server=cfg["server"])
if not logged_in:
    print("[-] MT5 Login failed:", mt5.last_error())
    mt5.shutdown()
    exit(1)

risk = DynamicNexusRisk(max_dd_pct=0.05, emergency_floor_pct=0.10, single_trade_risk_pct=0.01)
eval_res = risk.evaluate()

print("=" * 62)
print("     SHIVSOUL 10K ECOSYSTEM DYNAMIC INTEGRITY REPORT")
print("=" * 62)
for k, v in eval_res.items():
    print(f"  {k:18}: {v}")
print("-" * 62)

# Dynamic 1% risk sizing checks across our primary universe
for sym in ["EURUSD", "USDJPY", "GBPUSD", "XAUUSD", "BTCUSD"]:
    lot = risk.compute_dynamic_lot(sym, sl_points=250)
    print(f"  1% Dynamic Sizing [{sym:7} @ 250pts SL]: {lot:.2f} Lots")
print("=" * 62)

mt5.shutdown()