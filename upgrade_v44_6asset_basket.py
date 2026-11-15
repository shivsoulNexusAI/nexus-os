import json
import re
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
AUDIT_PATH = BASE_DIR / "audit_v44_focused_6plus_majors.json"
DAEMON_PATH = BASE_DIR / "nexus_multi_straddle_daemon.py"

audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
rankings = audit.get("rankings", [])
top3_fx_bases = audit.get("top3_fx", [])

# Resolve exact broker symbol names from rankings
resolved_map = {r["base"]: r["symbol"] for r in rankings if "base" in r and "symbol" in r}
core_syms = [resolved_map.get(b, b) for b in ("XAUUSD", "US30", "BTCUSD")]
fx_syms = [resolved_map.get(b, b) for b in top3_fx_bases][:3]

six_asset_basket = []
for s in core_syms + fx_syms:
    if s not in six_asset_basket:
        six_asset_basket.append(s)

code = DAEMON_PATH.read_text(encoding="utf-8")

# Replace CORE_TRIAD and COMPRESSION_MULT + MAX_ACTIVE_ASSETS cleanly
basket_repr = repr(six_asset_basket)
comp_dict = {s: (3.4 if "XAU" in s.upper() else 2.6) for s in six_asset_basket}
comp_repr = repr(comp_dict)

code, n1 = re.subn(
    r"^CORE_TRIAD\s*=\s*\[.*?\]",
    f"CORE_TRIAD = {basket_repr}",
    code,
    count=1,
    flags=re.MULTILINE,
)
code, n2 = re.subn(
    r"^COMPRESSION_MULT\s*=\s*\{.*?\}",
    f"COMPRESSION_MULT = {comp_repr}",
    code,
    count=1,
    flags=re.MULTILINE,
)
code, n3 = re.subn(
    r"^MAX_ACTIVE_ASSETS\s*=\s*\d+",
    "MAX_ACTIVE_ASSETS = 4",
    code,
    count=1,
    flags=re.MULTILINE,
)

# Expand win_streak fallback dictionary if needed
code = code.replace(
    'return {s: 0 for s in CORE_TRIAD}',
    'return {s: 0 for s in CORE_TRIAD}'
)

if n1 == 0 or n2 == 0:
    raise RuntimeError(f"Pattern match failed (n1={n1}, n2={n2}) in {DAEMON_PATH}")

DAEMON_PATH.write_text(code, encoding="utf-8")
print(f"[OK] Upgraded CORE_TRIAD -> {six_asset_basket}")
print(f"[OK] Updated COMPRESSION_MULT -> {comp_dict}")
print("[OK] Set MAX_ACTIVE_ASSETS = 4 (margin-safe concurrency cap for 6-asset basket)")