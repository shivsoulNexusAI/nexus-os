path = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\sovereign_nexus.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

import re

# Match photo_upload_handler and ensure exact 2-space indentation
pattern = r'async def photo_upload_handler\s*\([^)]*\):.*?(?=\s+msg\s*=)'
clean_handler_top = '''async def photo_upload_handler(
  update: Update, context: ContextTypes.DEFAULT_TYPE
):
  user_id = update.effective_user.id if update.effective_user else None
  print(f"\\n[!] INCOMING PHOTO RECEIVED from UID: {user_id}")
  if user_id != AUTHORIZED_UID:
    print(f"[!] REJECTED: UID {user_id} does not match AUTHORIZED_UID ({AUTHORIZED_UID})")
    return
  print(f"[+] ACCEPTED: Processing photo for authorized user {user_id}...")'''

fixed_content = re.sub(pattern, clean_handler_top, content, flags=re.DOTALL)

with open(path, "w", encoding="utf-8") as f:
    f.write(fixed_content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("[+] sovereign_nexus.py compiled cleanly with zero syntax errors!")
except Exception as e:
    print("[!] Syntax error:", e)
