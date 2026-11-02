import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# Define the clean, robust scan handler
clean_handler = """async def cmd_scan(update, context):
    try:
        matrix_msg, _ = build_institutional_fleet_matrix()
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = [
            [InlineKeyboardButton("🔄 Run Scan Again", callback_data="scan_now")],
            [InlineKeyboardButton("💼 Accounts Switchboard", callback_data="switchboard")]
        ]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(matrix_msg, reply_markup=InlineKeyboardMarkup(kb))
        elif update.message:
            await update.message.reply_text(matrix_msg, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        msg = f"❌ Scan generation error: {e}"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg)
        elif update.message:
            await update.message.reply_text(msg)
"""

# Replace existing cmd_scan or handle_scan function definition
pattern = r'async def (?:cmd_scan|handle_scan)\s*\([^)]*\):(?:\n(?:[ \t]*\n|[ \t]+[^\n]*\n))+'
if re.search(pattern, code):
    code = re.sub(pattern, clean_handler + "\n", code, count=1)
    print("[+] Successfully rewired cmd_scan to build_institutional_fleet_matrix().")
else:
    # If not found via regex, append it and ensure it is registered in CommandHandler
    code += "\n" + clean_handler
    print("[+] Appended clean cmd_scan handler.")

with open(path, "w", encoding="utf-8") as f:
    f.write(code)
