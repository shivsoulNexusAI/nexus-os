import os
import glob
import hashlib

eng_dir = r"C:\Quant-Nexus-Eng"
prod_dir = r"C:\Quant-Nexus-Prod"

def get_hash(path):
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def check_bom(path):
    if not path or not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        return f.read(3) == b"\xef\xbb\xbf"

def get_normalized_code_hash(path):
    """Normalizes directory references so path differences do not skew code parity."""
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read().replace(r"C:\Quant-Nexus-Eng", r"C:\Quant-Nexus-Prod")
        text = text.replace(r"C:/Quant-Nexus-Eng", r"C:/Quant-Nexus-Prod")
        text = text.replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

eng_files = {os.path.basename(p): p for p in glob.glob(os.path.join(eng_dir, "*.py"))}
prod_files = {os.path.basename(p): p for p in glob.glob(os.path.join(prod_dir, "*.py"))}
all_names = sorted(set(eng_files.keys()).union(prod_files.keys()))

print("\n" + "=" * 98)
print("            QUANTNEXUS CODEBASE INTEGRITY & PRODUCTION PARITY AUDIT (v2.0)            ")
print("=" * 98)
print(f"{'Module Name':<32} | {'Eng':<8} | {'Prod':<8} | {'BOM':<6} | {'Size (Eng/Prod)':<16} | {'Parity'}")
print("-" * 98)

unsynced = []
bom_warnings = []

for name in all_names:
    ep = eng_files.get(name)
    pp = prod_files.get(name)

    e_stat = "OK" if ep else "MISSING"
    p_stat = "OK" if pp else "MISSING"

    e_bom = check_bom(ep)
    p_bom = check_bom(pp)
    bom_flag = "WARN" if (e_bom or p_bom) else "CLEAN"
    if e_bom or p_bom:
        bom_warnings.append(name)

    e_size = f"{os.path.getsize(ep)/1024:.1f}k" if ep else "N/A"
    p_size = f"{os.path.getsize(pp)/1024:.1f}k" if pp else "N/A"
    size_str = f"{e_size} / {p_size}"

    if not pp:
        parity = "UNSYNCED (Not in Prod)"
        unsynced.append(name)
    elif not ep:
        parity = "ORPHAN (Prod Only)"
    else:
        norm_e = get_normalized_code_hash(ep)
        norm_p = get_normalized_code_hash(pp)
        if norm_e == norm_p:
            parity = "MATCH (Identical Logic)"
        else:
            parity = "DIVERGENT (Code Differs)"
            unsynced.append(name)

    print(f"{name:<32} | {e_stat:<8} | {p_stat:<8} | {bom_flag:<6} | {size_str:<16} | {parity}")

print("=" * 98)
print(f"Total Modules: {len(all_names)} | Divergent/Unsynced: {len(unsynced)} | BOM Warnings: {len(bom_warnings)}")
print("=" * 98 + "\n")
