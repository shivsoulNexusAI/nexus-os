path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

replacements = {
    "вњ…": "✅",
    "в‰Ґ": "≥",
    "рџ“Љ": "📊",
    "рџ’°": "💰",
    "вљЎ": "⚡",
    "рџ“Ќ": "📍",
    "рџЊђ": "🌐",
    "в”Ѓ": "━",
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

count = 0
for bad, good in replacements.items():
    if bad in text:
        text = text.replace(bad, good)
        count += 1
        print(f"[*] Replaced: {bad} -> {good}")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"[+] Total token types cleaned: {count}")
