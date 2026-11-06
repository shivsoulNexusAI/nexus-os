import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# 1. Clean all Mojibake sequences across keyboard buttons and messages
mojibake_map = {
    "РІвЂќРѓ": "━",
    "в”Ѓ": "━",
    "рџ”„": "🔄",
    "рџ’j": "💼",
    "рџ’°": "💰",
    "рџ“Љ": "📊",
    "вљЎ": "⚡",
    "рџ“Ќ": "📍",
    "вњ…": "✅",
    "в‰Ґ": "≥",
    "рџЊђ": "🌐",
    "рџ”Ґ": "🔥",
    "рџ”ґ": "🔴",
    "рџџў": "🟢",
    "вЏі": "⏳",
    "рџЋЇ": "🎯",
    "вЂў": "•",
    "рџ›ЎпёЏ": "🛡️",
    "вЏ±пёЏ": "⏱️",
    "рџљЂ": "🚀",
}

replaced = 0
for bad, good in mojibake_map.items():
    if bad in text:
        text = text.replace(bad, good)
        replaced += 1
print(f"[+] Cleaned {replaced} corrupt encoding token types.")

# 2. Add polling resilience without syntax conflicts
# Set robust timeout and prevent dropping queued mobile commands
if "app.run_polling(" in text:
    text = re.sub(
        r"app\.run_polling\(.*?\)",
        "app.run_polling(poll_interval=1.0, timeout=30, drop_pending_updates=False)",
        text,
        count=1
    )
    print("[+] Applied resilient polling timeout parameters.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Successfully updated telegram_interactive.py.")
