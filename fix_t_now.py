path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

import re

# 1. Ensure datetime is imported
if "import datetime" not in text:
    text = "import datetime\n" + text

# 2. Inject t_now at the start of render_leaderboard_card
fn_pattern = r'(def render_leaderboard_card\s*\([^)]*\):)'
replacement_fn = r'''\1
    import datetime as _dt
    t_now = _dt.datetime.now().strftime("%H:%M:%S")'''

if re.search(fn_pattern, text):
    text = re.sub(fn_pattern, replacement_fn, text, count=1)
    print("[+] Injected local t_now definition at top of render_leaderboard_card.")

# 3. Clean line 555 timestamp string
text = re.sub(r'lines\.append\(f["\']\\n.*?Last Scanned:.*?\{t_now\}["\']\)', 'lines.append(f"\\n⏱️ Last Scanned: {t_now}")', text)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] fix_t_now.py completed successfully.")
