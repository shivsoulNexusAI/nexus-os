from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\nexus_ship_core.py")
code = p.read_text(encoding="utf-8")

old_call = "register_tranche(pos.ticket, init_sl_dist)"
new_call = "register_tranche(pos.ticket, sleeve_id, init_sl_dist)"

if old_call in code:
    code = code.replace(old_call, new_call, 1)
    p.write_text(code, encoding="utf-8")
    print("[OK] Patched register_tranche(pos.ticket, sleeve_id, init_sl_dist) in nexus_ship_core.py")
else:
    print("[INFO] Already patched.")
