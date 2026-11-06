path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# 1. Update render_leaderboard_card to pull account telemetry if available
target_snippet = "def render_leaderboard_card("
if target_snippet in code:
    print("[*] Found render_leaderboard_card definition.")

# Add MT5 account info extraction inside render_leaderboard_card
patch_code = '''def render_leaderboard_card(scans, autopilot_status=None):
    account_info = None
    positions = []
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            account_info = mt5.account_info()
            positions = mt5.positions_get() or []
    except Exception:
        pass

    total_float = sum(p.profit for p in positions) if positions else 0.0
    equity = account_info.equity if account_info else 0.0
    balance = account_info.balance if account_info else 0.0
    pnl_sign = "+" if total_float >= 0 else ""
'''

# Replace signature block if not already patched
if "total_float = sum(p.profit for p in positions)" not in code:
    code = code.replace("def render_leaderboard_card(scans, autopilot_status=None):", patch_code, 1)
    print("[+] Injected live MT5 account telemetry extraction.")

# 2. Inject PnL metrics into the header/footer of the board text
old_header = 'lines = ["🌐 OMEGA FX: 5-ASSET", "INSTITUTIONAL LEADERBOARD", "━━━━━━━━━━━━━━━━━━━━━━"]'
new_header = '''pnl_tag = f"💰 ${equity:,.2f} | PnL: {pnl_sign}${total_float:.2f} ({len(positions)} Active)" if account_info else "📊 NEXUS MATRIX"
    lines = ["🌐 OMEGA FX: 5-ASSET", pnl_tag, "━━━━━━━━━━━━━━━━━━━━━━"]'''

if old_header in code:
    code = code.replace(old_header, new_header, 1)
    print("[+] Integrated live PnL and active positions header.")

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("[+] Dashboard PnL update applied successfully.")
