# -*- coding: utf-8 -*-
import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# 1. Fix the Stray "j" on the Switchboard Button
text = text.replace("💼j Accounts Switchboard", "💼 Accounts Switchboard")
text = text.replace("💼j", "💼")
text = re.sub(r'[\U0001F4BC]j\s*Accounts', '💼 Accounts', text)

# 2. Fix Keyboard Helper Function if explicitly named
text = re.sub(r'["\'][\U0001F4BC]?j?\s*Accounts Switchboard["\']', '"💼 Accounts Switchboard"', text)

# 3. Clean any lingering mojibake
text = text.replace("вЉЄ", "⚪")
text = text.replace("рџЋЇ", "🎯")
text = text.replace("рџ’", "💼")
text = text.replace("рџ›Ў", "🛡️")
text = text.replace("вЏ±", "⏱️")

# 4. Replace the entire render_leaderboard_card with the Institutional Underline Layout
new_render_fn = '''def render_leaderboard_card(scans, autopilot_status=None):
    import datetime as _dt
    t_now = _dt.datetime.now().strftime("%H:%M:%S")

    # Fetch fresh live account metrics
    acc = mt5.account_info()
    bal = acc.balance if acc else 10000.0
    eq = acc.equity if acc else bal
    mf = acc.margin_free if acc else bal

    # Query active MT5 positions
    all_positions = mt5.positions_get() or []
    open_sym_map = {p.symbol: p for p in all_positions}
    tot_pnl = sum([p.profit for p in all_positions])
    active_count = len(all_positions)

    lines = []
    lines.append("🏛️ <b>NEXUS HEDGE DESK | 5-ASSET MATRIX</b>")
    pnl_sign = "+" if tot_pnl >= 0 else ""
    lines.append(f"💼 <b>NAV:</b> ${eq:,.2f} | <b>Float PnL:</b> {pnl_sign}${tot_pnl:,.2f} ({active_count}/5 Active)")
    lines.append(f"🛡️ <b>Margin Free:</b> ${mf:,.2f} | <b>Balance:</b> ${bal:,.2f}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # Render Asset Rows (with Underline on Active/Locked Assets)
    rank = 1
    top_cand = None
    for item in (scans or []):
        s = item.get("symbol", "")
        direction = item.get("direction", "NEUTRAL")
        edge = item.get("edge", 50)
        rr = item.get("rr", 2.33)
        price = item.get("price", 0.0)
        sl = item.get("sl", 0.0)
        tp = item.get("tp", 0.0)
        lots = item.get("calculated_lots", 0.01)

        is_active = s in open_sym_map

        # Direction Icon
        if is_active:
            pos = open_sym_map[s]
            side_str = "BUY" if pos.type == 0 else "SELL"
            pos_pnl_sign = "+" if pos.profit >= 0 else ""
            # Two-line Underline styling for already triggered / active positions
            row = (
                f"<u>#{rank}: {s} | 🛡️ <b>ACTIVE POSITION ({side_str} {pos.volume}L)</b></u>\\n"
                f"   ↳ <i>Float: {pos_pnl_sign}${pos.profit:,.2f} | Open: ${pos.price_open:,.2f}</i>"
            )
        else:
            if direction == "BUY":
                icon = "🟢"
            elif direction == "SELL":
                icon = "🔴"
            else:
                icon = "⚪"

            status_tag = f"({edge}%)"
            if edge >= 75:
                status_tag = f"(✅ CLEARED {edge}%)"

            row = f"#{rank}: {s} | {icon} {direction} {status_tag} | RR: {rr:.2f}R"
            if top_cand is None and direction != "NEUTRAL":
                top_cand = item

        lines.append(row)
        rank += 1

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # Render Top Setup / Opportunity Block
    if top_cand:
        c_sym = top_cand.get("symbol", "N/A")
        c_dir = top_cand.get("direction", "BUY")
        c_edge = top_cand.get("edge", 0)
        c_entry = top_cand.get("price", 0.0)
        c_sl = top_cand.get("sl", 0.0)
        c_tp = top_cand.get("tp", 0.0)
        c_lots = top_cand.get("calculated_lots", 0.01)

        lines.append(f"🎯 <b>TOP OPPORTUNITY:</b> {c_sym} ({c_dir} @ {c_edge}%)")
        lines.append(f" • Entry: ${c_entry:,.3f}")
        lines.append(f" • SL: ${c_sl:,.3f} | TP: ${c_tp:,.3f}")
        lines.append(f" • Sizing: {c_lots:.2f} Lots (1% Risk)")
    else:
        lines.append("🎯 <b>TOP OPPORTUNITY:</b> Matrix Neutral (Awaiting Edge Expansion)")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # Autopilot & Position Lock Gate
    if autopilot_status:
        lines.append(f"<i>{autopilot_status}</i>")
    else:
        if top_cand and top_cand.get("symbol") in open_sym_map:
            lines.append(f"🛡️ <b>POSITION LOCK:</b> Active trade already running on {top_cand.get('symbol')}. Lock Engaged.")
        elif all_positions:
            running = list(open_sym_map.keys())
            lines.append(f"🛡️ <b>POSITION LOCK:</b> {len(running)} Positions running ({running}). Target Clear.")
        else:
            lines.append("🛡️ <b>POSITION LOCK:</b> Zero active positions. System clear to fire.")

    lines.append(f"\\n⏱️ Last Scanned: {t_now}")
    return "\\n".join(lines), get_scan_keyboard()'''

# Surgical Replacement of render_leaderboard_card
pattern = r'def render_leaderboard_card\s*\([^)]*\):.*?(?=\ndef [a-zA-Z0-9_]+\s*\(|\Z)'
if re.search(pattern, text, re.DOTALL):
    text = re.sub(pattern, new_render_fn + "\n\n", text, count=1, flags=re.DOTALL)
    print("[+] Successfully replaced render_leaderboard_card with Institutional Underline Layout.")
else:
    print("[-] Could not regex match render_leaderboard_card.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] File written successfully.")
