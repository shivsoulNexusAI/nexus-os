with open(r"C:\Quant-Nexus-Eng\nexus_institutional_production_master.py", "r", encoding="utf-8") as f:
    code = f.read()

# Dynamic filling mode detector function
filling_helper = """
def get_symbol_filling_mode(symbol: str):
    info = mt5.symbol_info(symbol)
    if not info:
        return mt5.ORDER_FILLING_FOK
    filling = info.filling_mode
    if filling & 1:
        return mt5.ORDER_FILLING_FOK
    elif filling & 2:
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_RETURN
"""

if "def get_symbol_filling_mode" not in code:
    code = code.replace("class AldemonStructureEngine:", filling_helper + "\nclass AldemonStructureEngine:")
    code = code.replace('"type_filling": mt5.ORDER_FILLING_IOC,', '"type_filling": get_symbol_filling_mode(symbol),')
    code = code.replace('"type_filling": mt5.ORDER_FILLING_IOC', '"type_filling": get_symbol_filling_mode(p.symbol)')

with open(r"C:\Quant-Nexus-Eng\nexus_institutional_production_master.py", "w", encoding="utf-8") as f:
    f.write(code)

print("[+] Successfully patched dynamic order filling mode (FOK/IOC/RETURN auto-resolution).")
