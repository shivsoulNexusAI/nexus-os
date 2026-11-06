path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Inspect lines around 888
for idx in range(max(0, 885 - 1), min(len(lines), 895)):
    line_str = lines[idx]
    stripped = line_str.lstrip(" ")
    # If it is execute_market_order or print, it belongs at 24 spaces
    if any(k in stripped for k in ["execute_market_order", "if ok:", "fired_orders.append", "sentinel_card ="]):
        if stripped.startswith("if ok:"):
            lines[idx] = " " * 24 + stripped
        elif stripped.startswith("fired_orders.append") or stripped.startswith("sentinel_card ="):
            lines[idx] = " " * 28 + stripped
        elif stripped.startswith("ok, res_msg, ticket ="):
            lines[idx] = " " * 24 + stripped
        elif stripped.startswith("print(f"):
            lines[idx] = " " * 24 + stripped

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Re-aligned trigger execution tail.")
