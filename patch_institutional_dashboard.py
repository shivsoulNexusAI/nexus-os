import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# 1. Clean all remaining button and neutral Mojibake tokens
text = text.replace("рџ’j", "💼")
text = text.replace("рџ”„", "🔄")
text = text.replace("вљ€", "⚪")
text = text.replace("рџ“Љ", "📊")
text = text.replace("рџ’°", "💰")

# Explicit string replacements for buttons to prevent CP1252 corruption
text = re.sub(r'InlineKeyboardButton\s*\(\s*text\s*=\s*["\'].*?Accounts Switchboard["\']', 'InlineKeyboardButton(text="💼 Accounts Switchboard"', text)
text = re.sub(r'InlineKeyboardButton\s*\(\s*text\s*=\s*["\'].*?Run Scan Again["\']', 'InlineKeyboardButton(text="🔄 Run Scan Again"', text)

# 2. Build Institutional Dashboard Header & Real-Time PnL Tracker
dashboard_patch = """
def render_leaderboard_card(scans, autopilot_status=None):
    account_info = None
    positions = []
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            account_info = mt5.account_info()
            positions = mt5.positions_get() or []
    except Exception:
        pass

    equity = account_info.equity if account_info else 0.0
    balance = account_info.balance if account_info else 0.0
    margin_free = account_info.margin_free if account_info else 0.0
    total_float = sum(p.profit for p in positions) if positions else 0.0
    pnl_sign = "+" if total_float >= 0 else ""
    active_count = len(positions)

    lines = [
        "🏛️ <b>NEXUS HEDGE DESK | 5-ASSET MATRIX</b>",
        f"💼 <b>NAV:</b> ${equity:,.2f} | <b>Float PnL:</b> {pnl_sign}${total_float:.2f} ({active_count}/5 Active)",
        f"🛡️ <b>Margin Free:</b> ${margin_free:,.2f} | <b>Balance:</b> ${balance:,.2f}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
"""

# Replace existing def render_leaderboard_card up to lines assignment
if "def render_leaderboard_card(" in text:
    pattern = r"def render_leaderboard_card\(.*?\):.*?(?=for |for candidate|\n\s*if not scans)"
    # We replace from header through the old lines array
    pattern_alt = r"def render_leaderboard_card\(.*?\):\n(?:[ \t]+.*?\n)*?[ \t]+lines\s*=\s*\[.*?\n(?:[ \t]+.*?\n)*?[ \t]+\]"
    if re.search(pattern_alt, text, re.DOTALL):
        text = re.sub(pattern_alt, dashboard_patch.strip(), text, count=1, flags=re.DOTALL)
        print("[+] Injected institutional header and live PnL engine.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Institutional dashboard and clean buttons saved.")
