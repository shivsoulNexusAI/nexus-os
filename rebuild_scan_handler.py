import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Clean replacement for the scan command handler using proper 4-space indentation
clean_scan_handler = """async def cmd_scan(update, context):
    try:
        matrix_msg, _ = build_institutional_fleet_matrix()
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = [
            [InlineKeyboardButton("🔄 Run Scan Again", callback_data="scan_now")],
            [InlineKeyboardButton("💼 Accounts Switchboard", callback_data="switchboard")]
        ]
        await update.message.reply_text(matrix_msg, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        await update.message.reply_text(f"❌ Scan error: {e}")
"""

# If cmd_scan or handle_scan exists around line 730, rewrite it cleanly
pattern = r'async def (?:cmd_scan|handle_scan|scan_handler)[^:]*:\n(?:[ \t]*\n|[ \t]+[^\n]*\n)+'
if re.search(pattern, text):
    text = re.sub(pattern, clean_scan_handler + "\n", text, count=1)
    print("[+] Successfully replaced corrupted scan handler block.")
else:
    print("[*] Specific async handler signature not matched by regex; checking line-by-line.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
