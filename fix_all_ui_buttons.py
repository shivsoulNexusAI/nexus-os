path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Exact mapping of all corrupt CP1252 sequences found in buttons and messages
replacements = {
    "рџ”„": "🔄",
    "рџ’j": "💼",
    "рџ’°": "💰",
    "рџ“Љ": "📊",
    "вљЎ": "⚡",
    "рџ“Ќ": "📍",
    "вњ…": "✅",
    "в‰Ґ": "≥",
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

replaced = 0
for bad, good in replacements.items():
    if bad in text:
        text = text.replace(bad, good)
        replaced += 1
        print(f"[+] Fixed token: {repr(bad)} -> {good}")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"[+] Cleaned {replaced} button/UI token types across the entire file.")
