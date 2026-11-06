path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Replace the generic daemon error print with full traceback
old_err = 'print(f"[!] Daemon error: {e}")'
new_err = 'import traceback; print(f"[!] Daemon error: {e}\\n{traceback.format_exc()}")'

if old_err in text:
    text = text.replace(old_err, new_err)
    print("[+] Enabled detailed traceback logging for daemon errors.")
else:
    # Fallback pattern
    import re
    text = re.sub(r'print\(f?"\[!\] Daemon error: \{[a-zA-Z0-9_]+\}"\)', new_err, text)
    print("[+] Applied regex pattern to reveal daemon traceback.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
