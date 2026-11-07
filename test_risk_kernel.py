import sys
sys.path.append(r"C:\Quant-Nexus-Eng")
import MetaTrader5 as mt5
from nexus_risk_kernel import risk_kernel

path = r"C:\MT5_HFT_278041671\terminal64.exe"
if mt5.initialize(path=path):
    allowed, reason, metrics = risk_kernel.audit_governance()
    print("\n=== RISK KERNEL GOVERNANCE AUDIT ===")
    print(f"• Gate Cleared: {allowed} ({reason})")
    print(f"• Market Regime: {metrics.get('regime')} | DD: {metrics.get('dd_pct', 0.0)*100:.2f}%")
    print(f"• Peak Equity HWM: ${metrics.get('hwm', 0.0):,.2f}")

    test_lots = risk_kernel.compute_position_size("XAUUSD247", stop_loss_points=250, edge=0.60)
    print(f"• Dynamic Kelly Sizing on XAUUSD247 (250 pts SL): {test_lots} Lots")
    print("====================================\n")
    mt5.shutdown()
else:
    print("[-] MT5 Connection Failed")