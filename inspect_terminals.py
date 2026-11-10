import MetaTrader5 as mt5

terminals = [
    r"C:\MT5_Quant_278017866\terminal64.exe",
    r"C:\MT5_Pending_278041169\terminal64.exe",
    r"C:\MT5_HFT_278041671\terminal64.exe",
    r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe",
    r"C:\Users\AdmVps\Documents\MetaTrader 5\terminal64.exe"
]

header = f"{'TERMINAL PATH':<45} | {'LOGIN':<11} | {'BALANCE':<10} | {'EQUITY':<10} | SERVER"
print(header)
print("=" * len(header))

for path in terminals:
    try:
        if not mt5.initialize(path=path):
            print(f"{path:<45} | OFFLINE     | ERR: {mt5.last_error()}")
            continue
        acc = mt5.account_info()
        if acc:
            print(f"{path:<45} | {str(acc.login):<11} | ${acc.balance:<9.2f} | ${acc.equity:<9.2f} | {acc.server}")
        else:
            print(f"{path:<45} | NO_AUTH     | $0.00      | $0.00      | N/A")
    except Exception as e:
        print(f"{path:<45} | ERROR       | {e}")
    finally:
        mt5.shutdown()