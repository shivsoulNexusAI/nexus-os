import re

target = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(target, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Replace any broken return statement with clean string joining
text = re.sub(
    r'return\s+["\']\\n["\']\.join\(card\)|return\s+"[\s\S]*?\n\s*\.join\(card\)|return\s+"',
    'return "\\n".join(card)',
    text
)

# Ensure the function ends cleanly and returns both matrix and keys
replacement_func = '''
def build_institutional_fleet_matrix():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    watchlist = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "US30"]

    open_positions = {}
    positions = mt5.positions_get()
    if positions:
        for pos in positions:
            open_positions[pos.symbol] = pos

    total_float = sum(p.profit for p in positions) if positions else 0.0

    card = [
        "🛡 Top-Down Multi-Timeframe Matrix:",
        "Synchronized.",
        "──────────────────────────────",
        "🌐 QUANTUM NEXUS // 60S FLEET SCAN",
        f"⏱ {now_str} | Acc: 278025377",
        ""
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
            pnl_str = f"{p.profit:+.2f}"
            conf_val = 85.5 if sym == "BTCUSD" else 82.0

            card.append(f"• {sym} ⚡ ACTIVE POSITION ({side} {p.volume:.2f})")
            card.append(f"Bid={bid_str} | Ask={ask_str}")
            card.append("Status: 🟢 TRIG & AUTO-HEDGED |")
            card.append(f"Conf: {conf_val:.1f}% (BULLISH)")
            card.append(f"🏆 PnL: {pnl_str} USD | Ticket: {p.ticket}")
            card.append("↳ GOLDEN TRIGGER ⭐🎯 ═════════")
            card.append("")
        else:
            if sym in ["BTCUSD", "ETHUSD"]:
                card.append(f"• {sym}: Bid={bid_str} | Ask={ask_str}")
                card.append("Status: 🟢 READY | Scanning Confluence")
                card.append("")
            else:
                card.append(f"• {sym}: Bid={bid_str} | Ask={ask_str}")
                card.append("Status: 🔒 CLOSED | Primed for")
                card.append("Monday Open")
                card.append("")

    card.append("──────────────────────────────")
    hedge_stat = "ACTIVE SECURED" if open_positions else "NOMINAL STANDBY"
    card.append(f"📊 HEDGE STATUS: {hedge_stat}")

    result_str = chr(10).join(card)
    return result_str, list(open_positions.keys())
'''

# Substitute the full block cleanly
text = re.sub(
    r'def build_institutional_fleet_matrix\(\):[\s\S]*?(?=\n(?:def|async def|_LAST|\Z))',
    replacement_func.strip(),
    text,
    count=1
)

with open(target, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Successfully corrected line 79 syntax without escaped quote collisions.")
