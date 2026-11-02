# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
    content = f.read().replace("\ufeff", "")

import re

# Ensure clean top imports
if "from nexus_risk_engine import risk_engine" not in content:
    content = "from nexus_risk_engine import risk_engine\n" + content

# Locate the 60s autonomous loop scan block
# Clean out any malformed orphaned blocks around [60s-SCAN ALL 5]
pattern = r'(\[60s-SCAN ALL 5\].*?\n)(.*?)(?=\n\s*(?:time\.sleep|await asyncio\.sleep|def |\Z))'

clean_block = r"""\1        # --- AUTONOMOUS RISK SENTINEL & TELEMETRIC BROADCAST ---
        try:
            primary_admin_id = 5279761713

            # 1. Evaluate & Ratchet Trailing Stops across active tickets
            risk_events = risk_engine.evaluate_and_ratchet()
            for ev in risk_events:
                ev_name = ev.get("event")
                sym = ev.get("symbol")
                tkt = ev.get("ticket")
                new_sl = ev.get("new_sl")
                pnl = ev.get("profit", 0.0)
                pnl_s = "+" if pnl >= 0 else ""
                alert_text = (
                    f"🛡️ <b>NEXUS RISK SENTINEL | {ev_name}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Ticket: <code>#{tkt}</code> | Asset: <b>{sym}</b>\n"
                    f"Dynamic Stop Ratchet: <code>${new_sl:,.2f}</code>\n"
                    f"Secured Floating PnL: <b>{pnl_s}${pnl:,.2f}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ <i>Autonomous Protection Engaged | Exness Core</i>"
                )
                if 'updater' in globals() and updater and updater.bot:
                    try:
                        updater.bot.send_message(chat_id=primary_admin_id, text=alert_text, parse_mode="HTML")
                    except Exception:
                        pass

            # 2. Render & Broadcast 60s Dashboard to Telegram
            card_text, card_markup = render_leaderboard_card(scans=scans, autopilot_status="AUTONOMOUS 60S CADENCE ACTIVE")
            if 'updater' in globals() and updater and updater.bot:
                try:
                    updater.bot.send_message(
                        chat_id=primary_admin_id,
                        text=card_text,
                        reply_markup=card_markup,
                        parse_mode="HTML"
                    )
                except Exception as b_err:
                    print(f"[!] Broadcast dispatch error: {b_err}")

            # 3. Dynamic Auto-Trigger >= 75% Edge on Unlocked Assets
            for item in (scans or []):
                s_edge = item.get("edge", 0)
                s_dir = item.get("direction", "NEUTRAL")
                s_sym = item.get("symbol", "")
                if s_edge >= 75 and s_dir in ["BUY", "SELL"]:
                    bot_obj = updater.bot if ('updater' in globals() and updater) else None
                    if 'execute_autonomous_signal' in globals():
                        execute_autonomous_signal(item, chat_id=primary_admin_id, bot_instance=bot_obj)
                    break
        except Exception as loop_err:
            print(f"[!] Autonomous loop telemetry error: {loop_err}")
"""

# Apply substitution
repaired = re.sub(pattern, clean_block, content, count=1, flags=re.DOTALL)

with open(path, "w", encoding="utf-8") as f:
    f.write(repaired)

print("[+] Repaired autonomous loop and aligned try/except blocks.")
