import sys
sys.path.append(r"C:\Quant-Nexus-Eng")
import MetaTrader5 as mt5
from deal_resolution_watcher import MT5_PATH, DealResolutionEngine

if mt5.initialize(path=MT5_PATH):
    print("\n=== DEAL RESOLUTION PIPELINE AUDIT ===")
    engine = DealResolutionEngine()
    print(f"• Baseline Ticket Cursor : #{engine.last_deal_ticket}")
    print("• Polling recent deals (past 24h)...")
    engine.poll_closed_deals()
    print(f"• Updated Ticket Cursor  : #{engine.last_deal_ticket}")
    print("[+] Pipeline audit executed cleanly.")
    print("======================================\n")
    mt5.shutdown()
else:
    print("[-] MT5 Initialization Failed")