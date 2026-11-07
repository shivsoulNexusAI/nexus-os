import sys
sys.path.append(r"C:\Quant-Nexus-Eng")
import MetaTrader5 as mt5
from nexus_risk_kernel import risk_kernel

path = r"C:\MT5_HFT_278041671\terminal64.exe"
if mt5.initialize(path=path):
    clear, reason, metrics = risk_kernel.audit_governance()
    regime = metrics.get('regime', 'UNKNOWN')
    hwm = metrics.get('hwm', 0.0)
    dd_pct = metrics.get('dd_pct', 0.0) * 100
    
    print("\n=== PILLAR 1: RISK GOVERNANCE & DYNAMIC SIZING AUDIT ===")
    print(f"• Governance Gate : {'CLEARED' if clear else 'LOCKED'} ({reason})")
    print(f"• Operating Regime : {regime}")
    print(f"• Peak Equity HWM  : ${hwm:,.2f}")
    print(f"• Current Drawdown : {dd_pct:.2f}%")
    print("-" * 55)

    symbols = ["XAUUSD247", "EURUSD", "GBPUSD", "BTCUSD"]
    for sym in symbols:
        lots = risk_kernel.compute_position_size(sym, stop_loss_points=250, edge=0.58)
        info = mt5.symbol_info(sym)
        vol_min = info.volume_min if info else 0.01
        vol_max = info.volume_max if info else 100.0
        print(f"• {sym:<10} | Dynamic Lot: {lots:>6.2f} | Allowed: [{vol_min} - {vol_max}]")
    print("========================================================\n")
    mt5.shutdown()
else:
    print("[-] MT5 Initialization Failed")