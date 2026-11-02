$pyCode = @'
import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# 1. Clean residual Mojibake tokens in keyboards & handlers
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

for bad, good in replacements.items():
    if bad in text:
        text = text.replace(bad, good)

# 2. Replace bare app.run_polling with resilient supervisor loop
old_launcher = """    app.run_polling(drop_pending_updates=True)"""

new_launcher = """    import time
    while True:
        try:
            print("[+] Starting resilient Telegram polling daemon...")
            app.run_polling(
                poll_interval=1.0,
                timeout=30,
                bootstrap_retries=-1,
                drop_pending_updates=False,
                close_loop=False
            )
        except Exception as e:
            print(f"[!] Polling supervisor caught exception: {e}. Reconnecting in 5s...")
            time.sleep(5)
            try:
                ensure_mt5()
            except Exception:
                pass"""

if "while True:" not in text and old_launcher in text:
    text = text.replace(old_launcher, new_launcher, 1)
    print("[+] Polling supervisor loop installed successfully.")
elif "app.run_polling" in text and "bootstrap_retries" not in text:
    text = re.sub(
        r'app\.run_polling\(.*?\)',
        'app.run_polling(poll_interval=1.0, timeout=30, bootstrap_retries=-1, drop_pending_updates=False)',
        text
    )
    print("[+] Updated app.run_polling with robust timeout & retry parameters.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Cleaned UI tokens and reinforced polling supervisor.")
