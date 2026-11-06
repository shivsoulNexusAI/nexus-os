# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

import re

# 1. Add import for nexus_risk_engine at top
if "from nexus_risk_engine import risk_engine" not in text:
    text = "from nexus_risk_engine import risk_engine\n" + text

# 2. Inject risk evaluation inside the autonomous 60s loop
loop_target = r'(print\s*\(\s*f"[^"]*?\[60s-SCAN ALL 5\].*?\))'
injection = """\\1
        # --- QUANT NEXUS RISK & TELEMETRIC PRODUCTION CORE ---
        try:
            risk_events = risk_engine.evaluate_and_ratchet()
            for ev in risk_events:
                ev_name = ev.get("event")
                sym = ev.get("symbol")
                tkt = ev.get("ticket")
                new_sl = ev.get("new_sl")
                pnl = ev.get("profit", 0.0)
                pnl_s = "+" if pnl >= 0 else ""
                alert_text = (
                    f"🛡️ <b>NEXUS RISK SENTINEL | {ev_name}</b>\\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
                    f"Ticket: <code>#{tkt}</code> | Asset: <b>{sym}</b>\\n"
                    f"Dynamic Stop Ratchet: <code>${new_sl:,.2f}</code>\\n"
                    f"Secured Floating PnL: <b>{pnl_s}${pnl:,.2f}</b>\\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
                    f"⚡ <i>Autonomous Protection Engaged | Exness Core</i>"
                )
                if 'updater' in globals() and updater.bot:
                    for uid in ADMIN_USER_IDS:
                        try:
                            updater.bot.send_message(chat_id=uid, text=alert_text, parse_mode="HTML")
                        except Exception:
                            pass
        except Exception as r_err:
            print(f"[!] Risk Sentinel Error: {r_err}")
"""

if "risk_engine.evaluate_and_ratchet()" not in text:
    text = re.sub(loop_target, injection, text, count=1)
    print("[+] Hooked risk_engine into autonomous 60s background loop.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Integration patch applied.")
