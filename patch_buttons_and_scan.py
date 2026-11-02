import os
import re

target = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(target, "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# 1. Clean corrupted inline button text
button_rep = {
    'рџ”„': '🔄',
    'рџ’j': '💼',
    'рџ’': '💼',
    'рџ“Љ': '📊',
    'рџ›ЎпёЏ': '🛡️',
    'рџ›Ў': '🛡️',
    'рџ”Ґ': '🔥',
    'рџЋЇ': '🎯',
    'в”Ѓ': '─',
    'вњ…': '✅'
}
for bad, good in button_rep.items():
    code = code.replace(bad, good)

# 2. Update /scan command handler to return the institutional card
# Replace the body of handle_scan or whatever function processes /scan
pattern = r'(async def (?:cmd_scan|handle_scan|scan_handler)[^:]*:\n)([\s\S]*?)(?=\n(?:async def|def|\Z))'
replacement = r'''\1    try:
        matrix_msg, _ = build_institutional_fleet_matrix()
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = [
            [InlineKeyboardButton("🔄 Run Scan Again", callback_data="scan_now")],
            [InlineKeyboardButton("💼 Accounts Switchboard", callback_data="switchboard")]
        ]
        await update.message.reply_text(matrix_msg, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        await update.message.reply_text(f"❌ Scan error: {e}")
'''

if re.search(pattern, code):
    code = re.sub(pattern, replacement, code, count=1)
    print("[+] Successfully rewired /scan handler to institutional layout!")
else:
    print("[*] Scan function signature slightly different; searching for reply text call...")
    code = re.sub(
        r'await update\.message\.reply_text\(.*dashboard_msg.*\)',
        r'msg, _ = build_institutional_fleet_matrix(); await update.message.reply_text(msg)',
        code
    )

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("[+] Script patched and saved cleanly with UTF-8 encoding.")
