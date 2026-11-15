import json
from pathlib import Path

micro_path = Path(r"C:\Quant-Nexus-Eng\microstructure_state.json")
daemon_path = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")

if not micro_path.exists():
    print("[-] microstructure_state.json does not exist yet.")
    raise SystemExit(1)

raw = json.loads(micro_path.read_text(encoding="utf-8"))
print("=== RAW microstructure_state.json ===")
print(json.dumps(raw, indent=2))

# Check whether symbols sit under "symbols" or at top-level
sym_map = raw.get("symbols") if isinstance(raw.get("symbols"), dict) else raw
sample_sym = next((s for s in ("XAUUSD", "US30", "BTCUSD") if isinstance(sym_map.get(s), dict)), None)

if not sample_sym:
    print("[-] No Core Triad symbol block found inside microstructure_state.json.")
    raise SystemExit(1)

sample = sym_map[sample_sym]
print(f"\n=== DETECTED KEYS FOR {sample_sym} ===")
print(list(sample.keys()))

# Verify compatibility with read_microstructure() in nexus_multi_straddle_daemon.py
code = daemon_path.read_text(encoding="utf-8")
old_fn = """    def read_microstructure(self, sym: str) -> dict:
        try:
            if MICRO_STATE_PATH.exists():
                data = json.loads(MICRO_STATE_PATH.read_text(encoding="utf-8"))
                return data.get("symbols", {}).get(sym, {})
        except Exception:
            pass
        return {}"""

new_fn = """    def read_microstructure(self, sym: str) -> dict:
        try:
            if MICRO_STATE_PATH.exists():
                data = json.loads(MICRO_STATE_PATH.read_text(encoding="utf-8"))
                sym_dict = data.get("symbols") if isinstance(data.get("symbols"), dict) else data
                st = sym_dict.get(sym, {}) if isinstance(sym_dict, dict) else {}
                if isinstance(st, dict):
                    return {
                        "delta_pct": float(st.get("delta_pct", st.get("aggressor_delta_pct", st.get("net_delta_pct", 0.0)))),
                        "inside_poc_chop": bool(st.get("inside_poc_chop", st.get("in_poc_chop", st.get("is_chop", False)))),
                        "vpoc": float(st.get("vpoc", st.get("poc", 0.0))),
                        "vah": float(st.get("vah", 0.0)),
                        "val": float(st.get("val", 0.0)),
                    }
        except Exception:
            pass
        return {}"""

if old_fn in code:
    daemon_path.write_text(code.replace(old_fn, new_fn, 1), encoding="utf-8")
    print("\n[OK] Upgraded read_microstructure() to handle both nested 'symbols' and top-level/alias schemas.")
else:
    print("\n[INFO] read_microstructure() already customized; verify keys above match.")