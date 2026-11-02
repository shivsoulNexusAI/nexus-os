# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
    lines = f.readlines()

# Locate target block [60s-SCAN ALL 5]
target_idx = -1
for i, line in enumerate(lines):
    if "[60s-SCAN ALL 5]" in line:
        target_idx = i
        break

if target_idx == -1:
    print("[-] [60s-SCAN ALL 5] marker not found.")
    exit(1)

base_len = len(lines[target_idx]) - len(lines[target_idx].lstrip())
b = " " * base_len
s1 = " " * (base_len + 4)
s2 = " " * (base_len + 8)
s3 = " " * (base_len + 12)

# Find boundary of existing injection
end_idx = target_idx + 1
while end_idx < len(lines):
    stripped = lines[end_idx].strip()
    curr_indent = len(lines[end_idx]) - len(lines[end_idx].lstrip())
    if stripped.startswith(("time.sleep", "await asyncio.sleep", "while ", "def ", "class ")) or (curr_indent < base_len and stripped):
        break
    end_idx += 1

persistent_block = [
    b + "# --- AUTONOMOUS TELEMETRY & PERSISTENT LIVE-DASHBOARD ---\n",
    b + "try:\n",
    s1 + "primary_admin_id = 5279761713\n",
    s1 + "global_last_msg_id = globals().get('LAST_DASHBOARD_MSG_ID', None)\n",
    s1 + "# 1. Trailing stops and Breakeven evaluation\n",
    s1 + "try:\n",
    s2 + "risk_events = risk_engine.evaluate_and_ratchet()\n",
    s2 + "for ev in (risk_events or []):\n",
    s3 + 'tkt = ev.get("ticket")\n',
    s3 + 'sym = ev.get("symbol")\n',
    s3 + 'new_sl = ev.get("new_sl")\n',
    s3 + 'pnl = ev.get("profit", 0.0)\n',
    s3 + 'pnl_s = "+" if pnl >= 0 else ""\n',
    s3 + 'r_alert = f"🛡️ <b>NEXUS RISK SENTINEL</b>\\n#{tkt} <b>{sym}</b> SL Ratcheted: <code>${new_sl:,.2f}</code> | Float: <b>{pnl_s}${pnl:,.2f}</b>"\n',
    s3 + 'if "updater" in globals() and updater and updater.bot:\n',
    s3 + '    updater.bot.send_message(chat_id=primary_admin_id, text=r_alert, parse_mode="HTML", timeout=8)\n',
    s1 + "except Exception as r_err:\n",
    s2 + 'print(f"[{t_now}] [!] Risk evaluation notice: {r_err}")\n',
    s1 + "\n",
    s1 + "# 2. Render & Live-Update Persistent Matrix Card\n",
    s1 + "try:\n",
    s2 + 'card_text, card_markup = render_leaderboard_card(scans=scans, autopilot_status="AUTONOMOUS 60S CADENCE ACTIVE")\n',
    s2 + 'bot_instance = updater.bot if ("updater" in globals() and updater and updater.bot) else None\n',
    s2 + 'if bot_instance:\n',
    s3 + 'updated = False\n',
    s3 + 'if global_last_msg_id:\n',
    s3 + '    try:\n',
    s3 + '        bot_instance.edit_message_text(chat_id=primary_admin_id, message_id=global_last_msg_id, text=card_text, reply_markup=card_markup, parse_mode="HTML", timeout=8)\n',
    s3 + '        updated = True\n',
    s3 + '    except Exception as edit_err:\n',
    s3 + '        # If message expired or unchanged, fall back to fresh message\n',
    s3 + '        pass\n',
    s3 + 'if not updated:\n',
    s3 + '    new_msg = bot_instance.send_message(chat_id=primary_admin_id, text=card_text, reply_markup=card_markup, parse_mode="HTML", timeout=8)\n',
    s3 + '    globals()["LAST_DASHBOARD_MSG_ID"] = new_msg.message_id\n',
    s3 + '    print(f"[{t_now}] [+] New Dashboard Card Pinned/Sent #{new_msg.message_id}")\n',
    s2 + 'else:\n',
    s3 + '    import requests\n',
    s3 + '    tok = globals().get("TELEGRAM_BOT_TOKEN") or globals().get("BOT_TOKEN")\n',
    s3 + '    if tok:\n',
    s3 + '        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": primary_admin_id, "text": card_text, "parse_mode": "HTML"}, timeout=8)\n',
    s1 + "except Exception as b_err:\n",
    s2 + 'print(f"[{t_now}] [!] Telemetry broadcast notice: {b_err}")\n',
    s1 + "\n",
    s1 + "# 3. Dynamic Auto-Trigger >= 75% Edge on Unlocked Assets\n",
    s1 + "for item in (scans or []):\n",
    s2 + 's_edge = item.get("edge", 0)\n',
    s2 + 's_dir = item.get("direction", "NEUTRAL")\n',
    s2 + 's_sym = item.get("symbol", "")\n',
    s2 + 'if s_edge >= 75 and s_dir in ["BUY", "SELL"] and s_sym not in active_syms:\n',
    s3 + 'bot_obj = updater.bot if ("updater" in globals() and updater) else None\n',
    s3 + 'execute_autonomous_signal(item, chat_id=primary_admin_id, bot_instance=bot_obj)\n',
    s3 + 'break\n',
    b + "except Exception as loop_err:\n",
    s1 + 'print(f"[{t_now}] [!] Autonomous loop iteration error: {loop_err}")\n'
]

lines = lines[:target_idx + 1] + persistent_block + lines[end_idx:]

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Persistent auto-refresh dashboard deployed successfully.")
