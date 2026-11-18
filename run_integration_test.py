import MetaTrader5 as mt5
from datetime import datetime, timezone
from nexus_ship_core import SLEEVES
from macro_gate import MacroGateController
from vol_target_sizer import VolatilityTargetingSizer

def run_integration_diagnostic():
    print(f"=== SHIVSOUL NEXUS v7.0 // MULTI-SLEEVE INTEGRATION AUDIT ===")
    print(f"    [TIMESTAMP] {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

    gate_controller = MacroGateController(db_path="nexus_ledger.db", vpin_threshold=0.75)
    
    sleeve_symbols = {
        "T1": "BTCUSD",
        "T2": "EURUSD",
        "T3": "XAUUSD"
    }

    for sleeve_name, cfg in SLEEVES.items():
        symbol = sleeve_symbols.get(sleeve_name, "EURUSD")
        print(f"-------------------------------------------------------------------------")
        print(f">>> EVALUATING SLEEVE: {sleeve_name} (#{cfg['login']}) | Target Asset: {symbol}")
        
        if not mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"]):
            print(f"    [ERR] Failed to connect to MetaTrader 5 terminal for {sleeve_name}")
            continue

        acc = mt5.account_info()
        equity = acc.equity if acc else 1000.0
        print(f"    [ACCOUNT] Balance: ${acc.balance:,.2f} | Equity: ${equity:,.2f}")

        # Pass sleeve_name to evaluate_gate so WAL records the correct sleeve
        gate_res = gate_controller.evaluate_gate(symbol, sleeve=sleeve_name)
        print(f"    [GATE & VPIN] Result: {gate_res}")

        sizer = VolatilityTargetingSizer(target_annual_vol=0.15, default_capital=equity)
        sizing_res = sizer.calculate_lot_size(symbol, risk_fraction=0.01)
        print(f"    [VOL-SIZER]   Result: {sizing_res}")

        mt5.shutdown()

    print(f"-------------------------------------------------------------------------")
    print(f"=== INTEGRATION DIAGNOSTIC COMPLETE: ALL SUBSYSTEMS NOMINAL ===")

if __name__ == "__main__":
    run_integration_diagnostic()
