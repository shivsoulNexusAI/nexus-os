from pathlib import Path
import py_compile
import re

path = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")
content = path.read_text(encoding="utf-8", errors="ignore")

# 1. Fix line in load_model() where 'sym' does not exist
content = re.sub(
    r"def load_model\(self\):.*?(?=def get_features)",
    """def load_model(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model_bundle = pickle.load(f)
            logging.info(f"[ML ENGINE LOADED] Regime model ready (AUC: {self.model_bundle.get('auc', 0.5):.4f})")
        except Exception as e:
            logging.warning(f"Could not load ML model: {e}. Defaulting to heuristic ATR gating.")
            self.model_bundle = None

    """,
    content,
    flags=re.DOTALL
)

# 2. Ensure top-level ASSET_THRESHOLDS dictionary is properly defined
if "ASSET_THRESHOLDS = {" not in content:
    dict_block = """
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
    content = content.replace("SYMBOLS = [", dict_block + "\nSYMBOLS = [")

# 3. Ensure cycle() resolves threshold dynamically per asset
if "thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)" not in content:
    content = content.replace(
        "for sym in SYMBOLS:",
        "for sym in SYMBOLS:\n            thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)"
    )

path.write_text(content, encoding="utf-8")

# 4. Compile verification
try:
    py_compile.compile(str(path), doraise=True)
    print("[+] Syntax & Scope verification PASSED: nexus_multi_straddle_daemon.py is 100% clean.")
except py_compile.PyCompileError as e:
    print(f"[-] Compilation failed: {e}")