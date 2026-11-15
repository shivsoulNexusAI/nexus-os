from pathlib import Path
import py_compile

targets = [
    Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py"),
    Path(r"C:\Quant-Nexus-Prod\core\nexus_multi_straddle_daemon.py")
]

for target in targets:
    if not target.exists():
        continue
    content = target.read_text(encoding="utf-8", errors="ignore")

    # Ensure import pickle is present at top
    if "import pickle" not in content:
        content = "import pickle\n" + content

    # Add fallback for feature_cols if model_bundle is None
    old_feat_access = 'feature_cols = self.model_bundle["feature_names"]'
    safe_feat_access = 'feature_cols = self.model_bundle["feature_names"] if self.model_bundle else ["atr14", "atr_base", "expansion_ratio", "spread_ratio"]'
    if old_feat_access in content:
        content = content.replace(old_feat_access, safe_feat_access)

    target.write_text(content, encoding="utf-8")
    
    try:
        py_compile.compile(str(target), doraise=True)
        print(f"[+] Successfully fixed pickle import and feature guard in {target.name}")
    except py_compile.PyCompileError as e:
        print(f"[-] Compilation error in {target.name}: {e}")