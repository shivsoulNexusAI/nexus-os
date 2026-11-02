# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
    text = f.read().replace("\ufeff", "").replace("\xa0", " ")

import re

# Ensure telegram broadcast doesn't hang on socket
target = "updater.bot.send_message(chat_id=primary_admin_id, text=card_text, reply_markup=card_markup, parse_mode='HTML')"
hardened = "updater.bot.send_message(chat_id=primary_admin_id, text=card_text, reply_markup=card_markup, parse_mode='HTML', timeout=10)"

if target in text:
    text = text.replace(target, hardened)
    print("[+] Added explicit timeout=10 to autonomous dispatch.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Hardening script executed.")
