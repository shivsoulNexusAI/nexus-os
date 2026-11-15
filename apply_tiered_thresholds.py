from pathlib import Path
import py_compile
import re

targets = [
    Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py"),
    Path(r"C:\Quant-Nexus-Prod\core\nexus_multi_straddle_daemon.py")
]

threshold_dict_code = """
# Calibrated Regime ML Decision Hurdles by Asset Profile
ASSET_THRESHOLDS = {
    "EURUSD": 0.65,
    "GBPUSD": 0.65,
    "USDJPY": 0.65,
    "US30":   0.68,
    "XAUUSD": 0.72,
    "BTCUSD": 0.72
}
DEFAULT_THRESHOLD = 0.65
"""

for target in targets:
    if not target.exists():
        continue
    content = target.read_text(encoding="utf-8", errors="ignore")

    # 1. Ensure ASSET_THRESHOLDS definition exists at the top level
    if "ASSET_THRESHOLDS" not in content:
        content = re.sub(r"(SYMBOLS\s*=\s*\[.*?\])", r"\1\n" + threshold_dict_code, content, flags=re.DOTALL)

    # 2. Patch threshold resolution in the asset loop
    # Match any fallback assignment like: thresh = ... or thresh = 0.65
    old_thresh_pat = r"thresh\s*=\s*self\.model_bundle\.get\([^)]+\)\s*if\s*self\.model_bundle\s*else\s*0\.65"
    new_thresh_code = "thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)"

    if re.search(old_thresh_pat, content):
        content = re.sub(old_thresh_pat, new_thresh_code, content)
    else:
        # Generic fallback replacement
        content = re.sub(r"thresh\s*=\s*0\.65", new_thresh_code, content)

    target.write_text(content, encoding="utf-8")
    
    try:
        py_compile.compile(str(target), doraise=True)
        print(f"[+] Successfully deployed Asset-Specific Thresholds to {target.name}")
    except py_compile.PyCompileError as e:
        print(f"[-] Compilation error on {target.name}: {e}")