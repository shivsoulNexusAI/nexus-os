with open(r"C:\Quant-Nexus-Eng\nexus_institutional_production_master.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
helper_inserted = False

universal_helper = """
def get_symbol_filling_mode(symbol: str):
    info = mt5.symbol_info(symbol)
    if not info:
        return mt5.ORDER_FILLING_FOK
    modes = info.filling_mode
    # Bit 0 (1): FOK, Bit 1 (2): IOC
    if modes & 2:
        return mt5.ORDER_FILLING_IOC
    elif modes & 1:
        return mt5.ORDER_FILLING_FOK
    else:
        return mt5.ORDER_FILLING_RETURN
"""

for line in lines:
    if "class AldemonStructureEngine:" in line and not helper_inserted:
        new_lines.append(universal_helper + "\n")
        helper_inserted = True
    
    if '"type_filling": mt5.ORDER_FILLING_IOC' in line:
        line = line.replace('"type_filling": mt5.ORDER_FILLING_IOC,', '"type_filling": get_symbol_filling_mode(symbol),')
        line = line.replace('"type_filling": mt5.ORDER_FILLING_IOC', '"type_filling": get_symbol_filling_mode(symbol)')
    new_lines.append(line)

with open(r"C:\Quant-Nexus-Eng\nexus_institutional_production_master.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("[+] Master script updated with universal multi-asset filling detection.")
