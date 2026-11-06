# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

import re

# 1. Strip the stray "j" from button text
text = text.replace("💼j Accounts Switchboard", "💼 Accounts Switchboard")
text = text.replace("💼j", "💼")
text = text.replace("вЉЄ", "⚪")

# 2. Complete clean replacement for render_leaderboard_card using clean raw blocks
clean_card_code = '''def render_leaderboard_card(scans, autopilot_status=None):
    import datetime as _dt
    t_now = _dt.datetime.now().strftime("%H:%M:%S")

    acc = mt5.account_info()
    bal = acc.balance if acc else 10000.0
    eq = acc.equity if acc else bal
    mf = acc.margin_free if acc else bal

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

    rank = 1
    top_cand = None
    for item in (scans or []):
        s = item.get("symbol", "")
        direction = item.get("direction", "NEUTRAL")
        edge = item.get("edge", 50)
        rr = item.get("rr", 2.33)

        if s in open_sym_map:
            pos = open_sym_map[s]
            side_str = "BUY" if pos.type == 0 else "SELL"
            pos_pnl_sign = "+" if pos.profit >= 0 else ""
            lines.append(f"<u>#{rank}: {s} | 🛡️ <b>ACTIVE POSITION ({side_str} {pos.volume:.2f}L)</b></u>")
            lines.append(f"   ↳ <i>Float: {pos_pnl_sign}${pos.profit:,.2f} | Open: ${pos.price_open:,.2f}</i>")
        else:
            icon = "🟢" if direction == "BUY" else ("🔴" if direction == "SELL" else "⚪")
            status_tag = f"(✅ CLEARED {edge}%)" if edge >= 75 else f"({edge}%)"
            lines.append(f"#{rank}: {s} | {icon} {direction} {status_tag} | RR: {rr:.2f}R")
            if top_cand is None and direction != "NEUTRAL":
                top_cand = item

        rank += 1

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

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

    if autopilot_status:
        lines.append(f"<i>{autopilot_status}</i>")
    else:
        if top_cand and top_cand.get("symbol") in open_sym_map:
            lines.append(f"🛡️ <b>POSITION LOCK:</b> Active trade already running on {top_cand.get('symbol')}. Lock Engaged.")
        elif all_positions:
            running = list(open_sym_map.keys())
            lines.append(f"🛡️ <b>POSITION LOCK:</b> {len(running)} Positions running ({running}). Target Clear.")
        else:
            lines.append("🛡️ <b>POSITION LOCK:</b> Zero active positions. Clear to fire.")

    lines.append("")
    lines.append(f"⏱️ Last Scanned: {t_now}")
    return "\\n".join(lines), get_scan_keyboard()'''

# Replace render_leaderboard_card cleanly
pattern = r'def render_leaderboard_card\s*\([^)]*\):.*?(?=\ndef [a-zA-Z0-9_]+\s*\(|\Z)'
if re.search(pattern, text, re.DOTALL):
    text = re.sub(pattern, clean_card_code + "\n\n", text, count=1, flags=re.DOTALL)
    print("[+] Replaced render_leaderboard_card safely.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Clean patch saved.")
