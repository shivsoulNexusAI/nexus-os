# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

import re

# 1. Surgical fix for ANY variation of "💼j" or stray characters in buttons
text = re.sub(r'["\'][^"\']*Accounts Switchboard["\']', '"💼 Accounts Switchboard"', text)
text = text.replace("💼j Accounts Switchboard", "💼 Accounts Switchboard")
text = text.replace("💼j", "💼")

# 2. Overhaul get_scan_keyboard function directly
scan_kb_pattern = r'def get_scan_keyboard\s*\([^)]*\):.*?(?=\ndef [a-zA-Z0-9_]+\s*\(|\Z)'
clean_kb = [
    "def get_scan_keyboard():",
    "    keyboard = [",
    "        [InlineKeyboardButton(\"🔄 Run Scan Again\", callback_data=\"rescan\")],",
    "        [InlineKeyboardButton(\"💼 Accounts Switchboard\", callback_data=\"accounts\")]",
    "    ]",
    "    return InlineKeyboardMarkup(keyboard)"
]
clean_kb_str = "\n".join(clean_kb)
if re.search(scan_kb_pattern, text, re.DOTALL):
    text = re.sub(scan_kb_pattern, clean_kb_str + "\n\n", text, count=1, flags=re.DOTALL)
    print("[+] Repaired get_scan_keyboard cleanly.")

# 3. Institutional Card Layout
clean_card_lines = [
    "def render_leaderboard_card(scans, autopilot_status=None):",
    "    import datetime as _dt",
    '    t_now = _dt.datetime.now().strftime("%H:%M:%S")',
    "",
    "    acc = mt5.account_info()",
    "    bal = acc.balance if acc else 10000.0",
    "    eq = acc.equity if acc else bal",
    "    mf = acc.margin_free if acc else bal",
    "",
    "    all_positions = mt5.positions_get() or []",
    "    open_sym_map = {p.symbol: p for p in all_positions}",
    "    tot_pnl = sum([p.profit for p in all_positions])",
    "    active_count = len(all_positions)",
    '    pnl_sign = "+" if tot_pnl >= 0 else ""',
    "",
    "    lines = []",
    '    lines.append("🏛️ <b>NEXUS HEDGE DESK | INSTITUTIONAL MATRIX</b>")',
    '    lines.append("────────────────────────────────")',
    '    lines.append(f"<code>NAV:    ${eq:,.2f}  | Float: {pnl_sign}${tot_pnl:,.2f}</code>")',
    '    lines.append(f"<code>Margin: ${mf:,.2f}  | Active: {active_count}/5 Active</code>")',
    '    lines.append("────────────────────────────────")',
    "",
    "    # Active in-market positions header",
    "    if open_sym_map:",
    '        lines.append("<b>⚡ LIVE MARKET EXECUTIONS (LOCKED)</b>")',
    "        for s_sym, pos in open_sym_map.items():",
    '            side_str = "BUY" if pos.type == 0 else "SELL"',
    '            pnl_s = "+" if pos.profit >= 0 else ""',
    '            lines.append(f"<u><b>{s_sym}</b> • {side_str} {pos.volume:.2f}L | Float: {pnl_s}${pos.profit:,.2f} | Open: {pos.price_open:,.2f}</u>")',
    '        lines.append("────────────────────────────────")',
    "",
    "    # Opportunity Matrix",
    '    lines.append("<b>📡 SCANNER FLEET | 60S CYCLE</b>")',
    "    rank = 1",
    "    top_cand = None",
    "    for item in (scans or []):",
    '        s = item.get("symbol", "")',
    '        direction = item.get("direction", "NEUTRAL")',
    '        edge = item.get("edge", 50)',
    '        rr = item.get("rr", 2.33)',
    "",
    "        if s in open_sym_map:",
    '            lines.append(f"<code>#{rank} {s:<7} [LOCKED] IN-POSITION</code>")',
    "        else:",
    '            icon = "🟢" if direction == "BUY" else ("🔴" if direction == "SELL" else "⚪")',
    '            status_tag = f"CLEARED {edge}%" if edge >= 75 else f"{edge}%"',
    '            lines.append(f"<code>#{rank} {s:<7} {icon} {direction:<4} ({status_tag}) RR:{rr:.2f}R</code>")',
    '            if top_cand is None and direction != "NEUTRAL":',
    "                top_cand = item",
    "        rank += 1",
    "",
    '    lines.append("────────────────────────────────")',
    "",
    "    # Top Execution Target Block",
    "    if top_cand:",
    '        c_sym = top_cand.get("symbol", "N/A")',
    '        c_dir = top_cand.get("direction", "BUY")',
    '        c_edge = top_cand.get("edge", 0)',
    '        c_entry = top_cand.get("price", 0.0)',
    '        c_sl = top_cand.get("sl", 0.0)',
    '        c_tp = top_cand.get("tp", 0.0)',
    '        c_lots = top_cand.get("calculated_lots", 0.01)',
    '        lines.append(f"🎯 <b>ALPHA TRIGGER: {c_sym} ({c_dir} @ {c_edge}%)</b>")',
    '        lines.append(f" • <b>Order Sizing:</b> <code>{c_lots:.2f} Lots (1% Risk Model)</code>")',
    '        lines.append(f" • <b>Entry:</b> <code>${c_entry:,.3f}</code>")',
    '        lines.append(f" • <b>SL:</b> <code>${c_sl:,.3f}</code> | <b>TP:</b> <code>${c_tp:,.3f}</code>")',
    "    else:",
    '        lines.append("🎯 <b>ALPHA TRIGGER:</b> <code>Matrix Balanced | Awaiting Edge Expansion</code>")',
    "",
    '    lines.append("────────────────────────────────")',
    "",
    "    # Autopilot Gate Status",
    "    if autopilot_status:",
    '        lines.append(f"<i>{autopilot_status}</i>")',
    "    else:",
    "        locked_names = list(open_sym_map.keys())",
    "        if locked_names:",
    '            locked_str = ", ".join(locked_names)',
    '            lines.append(f"🛡️ <b>SAFETY GATE:</b> Locked on [{locked_str}] | Scanner Ready.")',
    "        else:",
    '            lines.append("🛡️ <b>SAFETY GATE:</b> 0 Active Positions | Autonomous Fire Armed.")',
    "",
    '    lines.append(f"⏱️ <i>Updated: {t_now} | 60s Cadence</i>")',
    "    return chr(10).join(lines), get_scan_keyboard()"
]

card_pattern = r'def render_leaderboard_card\s*\([^)]*\):.*?(?=\ndef [a-zA-Z0-9_]+\s*\(|\Z)'
if re.search(card_pattern, text, re.DOTALL):
    text = re.sub(card_pattern, "\n".join(clean_card_lines) + "\n\n", text, count=1, flags=re.DOTALL)
    print("[+] Replaced render_leaderboard_card with Institutional Matrix layout.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] apply_executive_card.py applied successfully.")
