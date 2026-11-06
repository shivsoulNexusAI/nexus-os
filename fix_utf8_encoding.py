path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# Add explicit utf-8 environment handling at top of file if missing
utf8_preamble = """import sys
import io
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
"""

if "sys.stdout.reconfigure(encoding=" not in code:
    lines = code.splitlines(keepends=True)
    insert_idx = 0
    for idx, line in enumerate(lines[:30]):
        if line.startswith("import ") or line.startswith("from "):
            insert_idx = idx
            break
    lines.insert(insert_idx, utf8_preamble + "\n")
    code = "".join(lines)
    print("[+] Added UTF-8 stdout/stderr stream reconfigurer.")

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("[+] telegram_interactive.py saved with clean UTF-8 encoding.")
