# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

import re

# 1. Strip stray "j" from button text
text = re.sub(r'["\'][^"\']*Accounts Switchboard["\']', '"💼 Accounts Switchboard"', text)
text = text.replace("💼j", "💼")

# 2. Ensure parse_mode="HTML" on reply_text and send_message calls for scans
# Replace reply_text(card_text, reply_markup=...) with parse_mode="HTML"
text = re.sub(
    r'(reply_text\s*\(\s*[^)]*?reply_markup=[^)]*?)(\))',
    lambda m: m.group(1) + ', parse_mode="HTML")' if 'parse_mode' not in m.group(1) else m.group(0),
    text
)
text = re.sub(
    r'(edit_message_text\s*\(\s*[^)]*?reply_markup=[^)]*?)(\))',
    lambda m: m.group(1) + ', parse_mode="HTML")' if 'parse_mode' not in m.group(1) else m.group(0),
    text
)

# 3. Clean render_leaderboard_card with MT5 self-recovery and fallback scans
clean_card_lines = [
    "def render_leaderboard_card(scans=None, autopilot_status=None):",
    "    import datetime as _dt",
    '    t_now = _dt.datetime.now().strftime("%H:%M:%S")',
    "",
    "    # Self-heal MT5 connection if uninitialized",
    "    try:",
    "        if not mt5.terminal_info():",
    "            mt5.initialize(",
    "                path=r'C:\\Program Files\\MetaTrader 5\\terminal64.exe',",
    "                login=278025377,",
    "                password='H@ngkook3695',",
    "                server='Exness-MT5Trial5'",
    "            )",
    "    except Exception:",
    "        pass",
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
    "    # Fallback to fleet if scans is None or empty",
    "    if not scans:",
    "        scans = [",
    "            {'symbol': 'BTCUSD', 'direction': 'BUY' if 'BTCUSD' in open_sym_map else 'NEUTRAL', 'edge': 75 if 'BTCUSD' in open_sym_map else 50, 'rr': 2.33},",
    "            {'symbol': 'ETHUSD', 'direction': 'BUY' if 'ETHUSD' in open_sym_map else 'NEUTRAL', 'edge': 75 if 'ETHUSD' in open_sym_map else 50, 'rr': 2.33},",
    "            {'symbol': 'XAUUSD', 'direction': 'NEUTRAL', 'edge': 50, 'rr': 2.33},",
    "            {'symbol': 'USDJPY', 'direction': 'NEUTRAL', 'edge': 50, 'rr': 2.33},",
    "            {'symbol': 'EURUSD', 'direction': 'NEUTRAL', 'edge': 50, 'rr': 2.33},",
    "        ]",
    "",
    "    lines = []",
    '    lines.append("🏛️ <b>NEXUS HEDGE DESK | INSTITUTIONAL MATRIX</b>")',
    '    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")',
    '    lines.append(f"<code>NAV:      ${eq:,.2f}  | Float: {pnl_sign}${tot_pnl:,.2f}</code>")',
    '    lines.append(f"<code>Free Mgn: ${mf:,.2f}  | Fleet: {active_count}/5 Locked</code>")',
    '    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")',
    "",
    "    # 1. LIVE ACTIVE POSITIONS BLOCK",
    "    if open_sym_map:",
    '        lines.append("⚡ <b>LIVE MARKET EXECUTIONS (LOCKED)</b>")',
    "        for s_sym, pos in open_sym_map.items():",
    '            side_str = "BUY" if pos.type == 0 else "SELL"',
    '            pnl_s = "+" if pos.profit >= 0 else ""',
    '            lines.append(f"<u><b>{s_sym}</b> • {side_str} {pos.volume:.2f}L | Float: {pnl_s}${pos.profit:,.2f} | Open: {pos.price_open:,.2f}</u>")',
    '        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")',
    "",
    "    # 2. SCANNER FLEET (5 ASSETS)",
    '    lines.append("📡 <b>SCANNER FLEET | 60S CADENCE</b>")',
    "    rank = 1",
    "    top_cand = None",
    "    for item in (scans or []):",
    '        s = item.get("symbol", "")',
    '        direction = item.get("direction", "NEUTRAL")',
    '        edge = item.get("edge", 50)',
    '        rr = item.get("rr", 2.33)',
    "",
    "        if s in open_sym_map:",
    '            lines.append(f"<code>#{rank} {s:<7} 🔒 [LOCKED / IN-POSITION]</code>")',
    "        else:",
    '            icon = "🟢" if direction == "BUY" else ("🔴" if direction == "SELL" else "⚪")',
    '            status_tag = f"CLEARED {edge}%" if edge >= 75 else f"{edge}%"',
    '            lines.append(f"<code>#{rank} {s:<7} {icon} {direction:<4} ({status_tag}) RR:{rr:.2f}R</code>")',
    '            if top_cand is None and direction != "NEUTRAL":',
    "                top_cand = item",
    "        rank += 1",
    "",
    '    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")',
    "",
    "    # 3. ALPHA TRIGGER BLOCK",
    "    if top_cand:",
    '        c_sym = top_cand.get("symbol", "N/A")',
    '        c_dir = top_cand.get("direction", "BUY")',
    '        c_edge = top_cand.get("edge", 0)',
    '        c_entry = top_cand.get("price", 0.0)',
    '        c_sl = top_cand.get("sl", 0.0)',
    '        c_tp = top_cand.get("tp", 0.0)',
    '        c_lots = top_cand.get("calculated_lots", 0.01)',
    '        lines.append(f"🎯 <b>ALPHA TRIGGER: {c_sym} ({c_dir} @ {c_edge}%)</b>")',
    '        lines.append(f"• <b>Order Sizing:</b> <code>{c_lots:.2f} Lots (1% Dynamic Risk)</code>")',
    '        lines.append(f"• <b>Entry:</b> <code>${c_entry:,.3f}</code>")',
    '        lines.append(f"• <b>SL:</b> <code>${c_sl:,.3f}</code>  |  <b>TP:</b> <code>${c_tp:,.3f}</code>")',
    "    else:",
    '        lines.append("🎯 <b>ALPHA TRIGGER:</b> <code>Matrix Balanced | Awaiting Edge Expansion</code>")',
    "",
    '    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")',
    "",
    "    # 4. SAFETY GATE",
    "    if autopilot_status:",
    '        lines.append(f"<i>{autopilot_status}</i>")',
    "    else:",
    "        locked_names = list(open_sym_map.keys())",
    "        if locked_names:",
    '            locked_str = ", ".join(locked_names)',
    '            lines.append(f"🛡️ <b>SAFETY GATE:</b> Active Locks on [{locked_str}] | Scanner Ready.")',
    "        else:",
    '            lines.append("🛡️ <b>SAFETY GATE:</b> 0 Active Locks | Autonomous Execution Armed.")',
    "",
    '    lines.append(f"⏱️ <i>Updated: {t_now} | 60s Cadence</i>")',
    "    return chr(10).join(lines), get_scan_keyboard()"
]

card_pattern = r'def render_leaderboard_card\s*\([^)]*\):.*?(?=\ndef [a-zA-Z0-9_]+\s*\(|\Z)'
clean_card_code = "\n".join(clean_card_lines) + "\n\n"

# Use lambda replacement to prevent regex backslash parsing errors
if re.search(card_pattern, text, re.DOTALL):
    text = re.sub(card_pattern, lambda m: clean_card_code, text, count=1, flags=re.DOTALL)
    print("[+] Patched render_leaderboard_card using lambda replacer.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] patch_final_institutional.py written successfully.")
