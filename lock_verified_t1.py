from pathlib import Path
import MetaTrader5 as mt5

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
VERIFIED_T1_PATH = r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe"
OLD_LOCKED_PATH  = r"C:\MT5_HFT_278041671\terminal64.exe"

# 1. Re-point omega_apex_scanner.py to the verified AlgoTrading=True terminal
scanner_path = BASE_DIR / "omega_apex_scanner.py"
if scanner_path.exists():
    code = scanner_path.read_text(encoding="utf-8")
    code = code.replace(OLD_LOCKED_PATH, VERIFIED_T1_PATH)
    code = code.replace("if not mt5.initialize():", f'if not mt5.initialize(path=r"{VERIFIED_T1_PATH}"):')
    scanner_path.write_text(code, encoding="utf-8")
    print(f"[OK] omega_apex_scanner.py locked to: {VERIFIED_T1_PATH}")

# 2. Also bind quantum_institutional_pro.py to the exact same path if it uses generic mt5.initialize()
qip_path = BASE_DIR / "quantum_institutional_pro.py"
if qip_path.exists():
    qcode = qip_path.read_text(encoding="utf-8")
    if "mt5.initialize()" in qcode:
        qcode = qcode.replace("mt5.initialize()", f'mt5.initialize(path=r"{VERIFIED_T1_PATH}")')
        qip_path.write_text(qcode, encoding="utf-8")
        print(f"[OK] quantum_institutional_pro.py locked to: {VERIFIED_T1_PATH}")

# 3. Final live verification on VERIFIED_T1_PATH
if mt5.initialize(path=VERIFIED_T1_PATH):
    acc = mt5.account_info()
    term = mt5.terminal_info()
    print(f"\n[LIVE READY] Account: #{acc.login} | Balance: ${acc.balance:,.2f}")
    print(f"[LIVE READY] Master Toolbar Algo Trading: {term.trade_allowed}")
    mt5.shutdown()
