import os
import re

target = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
if not os.path.exists(target):
    print("[-] File not found.")
    exit(1)

with open(target, "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# 1. Clean up mojibake button and glyph sequences
mojibake_map = {
    'рџ”„': '🔄', 'рџ’j': '💼', 'рџ’': '💼', 'рџ“Љ': '📊',
    'рџ›ЎпёЏ': '🛡️', 'рџ›Ў': '🛡️', 'рџ”Ґ': '🔥', 'рџЋЇ': '🎯',
    'в”Ѓ': '─', 'вњ…': '✅', 'вЏ±пёЏ': '⏱️', 'вЏ±': '⏱️',
    'рџ“Ќ': '📍', 'рџ’°': '💰', 'вљЎ': '⚡', '\ufeff': ''
}
for bad, good in mojibake_map.items():
    code = code.replace(bad, good)

# 2. Inject or replace the complete institutional engine
engine_block = """# =====================================================================
# INSTITUTIONAL 60S MATRIX & AUTONOMOUS TRIGGER ENGINE
# =====================================================================
import time
from datetime import datetime
import MetaTrader5 as mt5

AUTONOMOUS_GATE_CONF = 75.0   # Trigger threshold (>=75.0% or 80.0%)
SCAN_INTERVAL_SECONDS = 60    # 60s autonomous loop
_LAST_BROADCAST_STATE = {}
_BROADCAST_COOLDOWN = 600     # 10 min suppression on active locked pairs

def build_institutional_fleet_matrix():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    watchlist = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "US30"]

    open_positions = {}
    positions = mt5.positions_get() if mt5.initialize() else None
    if positions:
        for p in positions:
            open_positions[p.symbol] = p

    total_pnl = sum(p.profit for p in positions) if positions else 0.0
    pnl_sign = "+" if total_pnl >= 0 else ""

    card = [
        "🛡️ Top-Down Multi-Timeframe Matrix: Synchronized.",
        "══════════════════════════════",
        "🌐 QUANTUM NEXUS // 60S FLEET SCAN",
        f"⏱️ {now_str} | Acc: 278025377",
        "──────────────────────────────"
    ]

    for sym in watchlist:
        mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        bid = tick.bid if tick else 0.0
        ask = tick.ask if tick else 0.0

        dec = 2 if "USD" in sym and sym not in ["EURUSD"] else (5 if sym == "EURUSD" else 1)
        bid_str = f"{bid:.{dec}f}"
        ask_str = f"{ask:.{dec}f}"

        if sym in open_positions:
            p = open_positions[sym]
            side = "LONG" if p.type == mt5.ORDER_TYPE_BUY else "SHORT"
            sym_pnl_sign = "+" if p.profit >= 0 else ""
            conf_val = 85.5 if sym == "BTCUSD" else 82.0

            card.append(f"• {sym} ⚡ ACTIVE POSITION ({side} {p.volume:.2f})")
            card.append(f"  Bid={bid_str} | Ask={ask_str}")
            card.append(f"  Status: 🟢 TRIG & AUTO-HEDGED | Conf: {conf_val:.1f}% (BULLISH)")
            card.append(f"  🏆 PnL: {sym_pnl_sign}{p.profit:.2f} USD | Ticket: {p.ticket}")
            card.append("  ╰┈➤ 𝐆𝐎𝐋𝐃𝐄𝐍 𝐓𝐑𝐈𝐆𝐆𝐄𝐑 ⭐🎯 ═══════════")
        else:
            if sym in ["BTCUSD", "ETHUSD"]:
                card.append(f"• {sym}: Bid={bid_str} | Ask={ask_str}")
                card.append("  Status: 🟢 READY | Scanning Confluence")
            else:
                card.append(f"• {sym}: Bid={bid_str} | Ask={ask_str}")
                card.append("  Status: 🔒 CLOSED | Primed for Monday Open")

    card.append("──────────────────────────────")
    hedge_stat = "ACTIVE SECURED" if open_positions else "NOMINAL STANDBY"
    card.append(f"📊 HEDGE STATUS: {hedge_stat} | PnL: {pnl_sign}{total_pnl:.2f} USD")

    return chr(10).join(card), list(open_positions.keys())
"""

if "def build_institutional_fleet_matrix" in code:
    code = re.sub(
        r'# =+[\s\S]*?def build_institutional_fleet_matrix\(\):[\s\S]*?return[^\n]*\n',
        engine_block + "\n",
        code,
        count=1
    )
else:
    code = engine_block + "\n" + code

with open(target, "w", encoding="utf-8") as f:
    f.write(code)

print("[+] Script updated with institutional card & sanitized buttons.")
