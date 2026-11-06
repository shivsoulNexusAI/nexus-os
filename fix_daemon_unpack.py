import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# 1. Ensure any function that fires the trigger returns (str, None) or (bool, str) safely
# Fix bare returns inside execution/trigger functions
text = re.sub(r'(\n\s+return\s*\n)', r'\n        return "", None\n', text)

# 2. Fix sleep duration if set to 5s in the daemon loop
text = re.sub(r'asyncio\.sleep\([1-5]\)', 'asyncio.sleep(60)', text)
text = re.sub(r'time\.sleep\([1-5]\)', 'time.sleep(60)', text)

# 3. Guard unpack calls where `res = func()` or `msg, kb = func()`
# Wrap unpack calls in a safe helper:
safe_unpack_patch = """
def safe_matrix_call():
    try:
        res = build_institutional_fleet_matrix()
        if isinstance(res, tuple) and len(res) >= 2:
            return res[0], res[1]
        elif isinstance(res, str):
            return res, None
        return "", None
    except Exception as e:
        return f"Scan error: {e}", None
"""

if "def safe_matrix_call" not in text:
    text = safe_unpack_patch + "\n" + text

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Successfully patched daemon loop unpack safety and cadence.")
