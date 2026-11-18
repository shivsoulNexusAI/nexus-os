from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\omega_apex_scanner.py")
code = p.read_text(encoding="utf-8")

# Define alpha_status right before building the Telegram message block
target_msg = '    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")'
replacement_msg = '    alpha_status = " | ".join(triggers) if triggers else "Matrix Balanced | Awaiting Edge"\n    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")'

if target_msg in code:
    code = code.replace(target_msg, replacement_msg, 1)
    p.write_text(code, encoding="utf-8")
    print("[OK] Fixed alpha_status variable scope in omega_apex_scanner.py")
