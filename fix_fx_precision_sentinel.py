from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")

# 1. Replace USDJPY -> USDCHF in microstructure_sentinel.py so all 6 V4.4 assets stream live delta_pct
sent_path = BASE_DIR / "microstructure_sentinel.py"
if sent_path.exists():
    s_code = sent_path.read_text(encoding="utf-8")
    if "USDJPY" in s_code and "USDCHF" not in s_code:
        s_code = s_code.replace("USDJPY", "USDCHF")
        sent_path.write_text(s_code, encoding="utf-8")
        print("[OK] Updated microstructure_sentinel.py: replaced USDJPY -> USDCHF (exact 6-asset V4.4 match).")
    else:
        print("[INFO] microstructure_sentinel.py already includes USDCHF.")

# 2. Update log formatting in nexus_multi_straddle_daemon.py from :.2f to :.5f on box_range/ATR so FX pip ranges never display as 0.00
daemon_path = BASE_DIR / "nexus_multi_straddle_daemon.py"
d_code = daemon_path.read_text(encoding="utf-8")
old_log = 'logging.info(f"[V4.4 SKIP NON-COILED] {sym} Asian box={box_range:.2f} vs {max_mult}x ATR56={atr_56 * max_mult:.2f}")'
new_log = 'logging.info(f"[V4.4 SKIP NON-COILED] {sym} Asian box={box_range:.5f} vs {max_mult}x ATR56={atr_56 * max_mult:.5f}")'
if old_log in d_code:
    d_code = d_code.replace(old_log, new_log)
    daemon_path.write_text(d_code, encoding="utf-8")
    print("[OK] Updated Asian box log precision to 5 decimals (.5f) for exact FX pip visibility.")