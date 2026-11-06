path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "rb") as f:
    raw = f.read()

# Dictionary of corrupted CP1252 string representations to clean UTF-8 emojis
replacements = {
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

text = raw.decode("utf-8", errors="ignore")
modified = False
for bad, good in replacements.items():
    if bad in text:
        text = text.replace(bad, good)
        modified = True
        print(f"[*] Repaired Mojibake token: {bad} -> {good}")

if modified:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("[+] Successfully replaced all corrupted symbols with standard Unicode emojis.")
else:
    print("[*] No literal Mojibake tokens found in file; issue was solely runtime encoding.")
