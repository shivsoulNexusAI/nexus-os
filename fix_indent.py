# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"

with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
    lines = f.readlines()

target_idx = -1
for i, line in enumerate(lines):
    if "[60s-SCAN ALL 5]" in line:
        target_idx = i
        break

if target_idx == -1:
    print("[-] [60s-SCAN ALL 5] marker not found.")
    exit(1)

# Detect base indentation of the print statement
scan_line = lines[target_idx]
base_len = len(scan_line) - len(scan_line.lstrip())
b = " " * base_len
s1 = " " * (base_len + 4)
s2 = " " * (base_len + 8)
s3 = " " * (base_len + 12)

print(f"[+] Detected base indent: {base_len} spaces at line {target_idx + 1}")

# Locate end of the current malformed block
end_idx = target_idx + 1
while end_idx < len(lines):
    stripped = lines[end_idx].strip()
    curr_indent = len(lines[end_idx]) - len(lines[end_idx].lstrip())
    if stripped.startswith(("time.sleep", "await asyncio.sleep", "while ", "def ", "class ")) or (curr_indent < base_len and stripped):
        break
    end_idx += 1

clean_block = [
    b + "# --- AUTONOMOUS RISK SENTINEL & TELEMETRIC BROADCAST ---\n",
    b + "try:\n",
    s1 + "primary_admin_id = 5279761713\n",
    s1 + "risk_events = risk_engine.evaluate_and_ratchet()\n",
    s1 + "for ev in (risk_events or []):\n",
    s2 + 'ev_name = ev.get("event")\n',
    s2 + 'sym = ev.get("symbol")\n',
    s2 + 'tkt = ev.get("ticket")\n',
    s2 + 'new_sl = ev.get("new_sl")\n',
    s2 + 'pnl = ev.get("profit", 0.0)\n',
    s2 + 'pnl_s = "+" if pnl >= 0 else ""\n',
    s2 + "alert_text = (\n",
    s3 + 'f"🛡️ <b>NEXUS RISK SENTINEL | {ev_name}</b>\\n"\n',
    s3 + '"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"\n',
    s3 + 'f"Ticket: <code>#{tkt}</code> | Asset: <b>{sym}</b>\\n"\n',
    s3 + 'f"Dynamic Stop Ratchet: <code>${new_sl:,.2f}</code>\\n"\n',
    s3 + 'f"Secured Floating PnL: <b>{pnl_s}${pnl:,.2f}</b>\\n"\n',
    s3 + '"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"\n',
    s3 + '"⚡ <i>Autonomous Protection Engaged | Exness Core</i>"\n',
    s2 + ")\n",
    s2 + 'if "updater" in globals() and updater and updater.bot:\n',
    s3 + "try:\n",
    s3 + '    updater.bot.send_message(chat_id=primary_admin_id, text=alert_text, parse_mode="HTML")\n',
    s3 + "except Exception:\n",
    s3 + "    pass\n",
    s1 + 'card_text, card_markup = render_leaderboard_card(scans=scans, autopilot_status="AUTONOMOUS 60S CADENCE ACTIVE")\n',
    s1 + 'if "updater" in globals() and updater and updater.bot:\n',
    s2 + "try:\n",
    s2 + '    updater.bot.send_message(chat_id=primary_admin_id, text=card_text, reply_markup=card_markup, parse_mode="HTML")\n',
    s2 + "except Exception as b_err:\n",
    s2 + '    print(f"[!] Broadcast dispatch error: {b_err}")\n',
    s1 + "for item in (scans or []):\n",
    s2 + 's_edge = item.get("edge", 0)\n',
    s2 + 's_dir = item.get("direction", "NEUTRAL")\n',
    s2 + 's_sym = item.get("symbol", "")\n',
    s2 + 'if s_edge >= 75 and s_dir in ["BUY", "SELL"] and s_sym not in active_syms:\n',
    s3 + 'bot_obj = updater.bot if ("updater" in globals() and updater) else None\n',
    s3 + "execute_autonomous_signal(item, chat_id=primary_admin_id, bot_instance=bot_obj)\n",
    s3 + "break\n",
    b + "except Exception as loop_err:\n",
    s1 + 'print(f"[!] Autonomous loop telemetry error: {loop_err}")\n'
]

lines = lines[:target_idx + 1] + clean_block + lines[end_idx:]

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Replaced block with perfectly aligned indentation.")
