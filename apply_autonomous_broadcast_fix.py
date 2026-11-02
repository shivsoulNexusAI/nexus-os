# -*- coding: utf-8 -*-
path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
    text = f.read().replace("\ufeff", "").replace("\xa0", " ")

# 1. Clean top-level risk_engine import
if "from nexus_risk_engine import risk_engine" not in text:
    text = "from nexus_risk_engine import risk_engine\n" + text

# 2. Add execution helper cleanly using literal replacement (avoids re.error)
exec_helper = """
def execute_autonomous_signal(candidate, chat_id=None, bot_instance=None):
    import MetaTrader5 as mt5
    if not mt5.terminal_info():
        mt5.initialize(
            path=r"C:\\Program Files\\MetaTrader 5\\terminal64.exe",
            login=278025377,
            password="H@ngkook3695",
            server="Exness-MT5Trial5"
        )

    symbol = candidate.get('symbol')
    direction = candidate.get('direction', 'BUY').upper()
    edge = candidate.get('edge', 0)

    open_positions = mt5.positions_get() or []
    if any(p.symbol == symbol for p in open_positions):
        print(f"[*] Auto-Trigger: {symbol} is already locked. Skipping duplicate.")
        return False

    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return False

    if not sym_info.visible:
        mt5.symbol_select(symbol, True)

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False

    order_type = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == 'BUY' else tick.bid
    point = sym_info.point
    atr = risk_engine.calculate_atr(symbol)

    sl_dist = atr * 1.8
    tp_dist = atr * 3.6
    sl = round(price - sl_dist if direction == 'BUY' else price + sl_dist, sym_info.digits)
    tp = round(price + tp_dist if direction == 'BUY' else price - tp_dist, sym_info.digits)

    lots = risk_engine.calculate_kelly_lots(symbol, edge, sl_dist)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": float(price),
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": 9992026,
        "comment": f"Nexus Alpha {edge}%",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[+++] AUTONOMOUS EXECUTION: #{res.order} {symbol} {direction} {lots}L @ {price}")
        if bot_instance and chat_id:
            alert = (
                f"🚀 <b>AUTONOMOUS ALPHA TRIGGER EXECUTED</b>\\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
                f"Asset: <b>{symbol}</b> | Action: <b>{direction}</b>\\n"
                f"Edge Confidence: <code>{edge}% CONFLUENCE</code>\\n"
                f"Order Volume: <code>{lots:.2f} Lots (Dynamic Kelly)</code>\\n"
                f"Entry Price: <code>${price:,.3f}</code>\\n"
                f"Stop Loss:   <code>${sl:,.3f}</code>\\n"
                f"Take Profit: <code>${tp:,.3f} (2.0R Target)</code>\\n"
                f"Ticket: <code>#{res.order}</code>\\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n"
                f"⚡ <i>Quant Nexus Autonomous Engine Armed</i>"
            )
            try:
                bot_instance.send_message(chat_id=chat_id, text=alert, parse_mode='HTML')
            except Exception as e:
                print(f"[!] Alert dispatch error: {e}")
        return True
    return False
\n"""

if "def execute_autonomous_signal(" not in text:
    anchor = "def render_leaderboard_card"
    if anchor in text:
        text = text.replace(anchor, exec_helper + anchor, 1)
        print("[+] execute_autonomous_signal injected before render_leaderboard_card.")

# 3. Clean line 1999+ around [60s-SCAN ALL 5]
lines = text.splitlines(keepends=True)
target_idx = -1
for i, line in enumerate(lines):
    if "[60s-SCAN ALL 5]" in line:
        target_idx = i
        break

if target_idx != -1:
    print(f"[+] Found [60s-SCAN ALL 5] at index {target_idx + 1}")
    # Determine the end of the malformed block (find next time.sleep or while loop boundary)
    end_idx = target_idx + 1
    while end_idx < len(lines):
        line_strip = lines[end_idx].strip()
        if line_strip.startswith(("time.sleep", "await asyncio.sleep", "def ", "class ")) or line_strip.startswith("while "):
            break
        end_idx += 1

    clean_block = [
        "                 # --- AUTONOMOUS RISK SENTINEL & TELEMETRIC BROADCAST ---\n",
        "                 try:\n",
        "                     primary_admin_id = 5279761713\n",
        "                     risk_events = risk_engine.evaluate_and_ratchet()\n",
        "                     for ev in (risk_events or []):\n",
        "                         ev_name = ev.get('event')\n",
        "                         sym = ev.get('symbol')\n",
        "                         tkt = ev.get('ticket')\n",
        "                         new_sl = ev.get('new_sl')\n",
        "                         pnl = ev.get('profit', 0.0)\n",
        "                         pnl_s = '+' if pnl >= 0 else ''\n",
        "                         alert_text = (\n",
        "                             f'🛡️ <b>NEXUS RISK SENTINEL | {ev_name}</b>\\n'\n",
        "                             f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n'\n",
        "                             f'Ticket: <code>#{tkt}</code> | Asset: <b>{sym}</b>\\n'\n",
        "                             f'Dynamic Stop Ratchet: <code>${new_sl:,.2f}</code>\\n'\n",
        "                             f'Secured Floating PnL: <b>{pnl_s}${pnl:,.2f}</b>\\n'\n",
        "                             f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━\\n'\n",
        "                             f'⚡ <i>Autonomous Protection Engaged | Exness Core</i>'\n",
        "                         )\n",
        "                         if 'updater' in globals() and updater and updater.bot:\n",
        "                             try:\n",
        "                                 updater.bot.send_message(chat_id=primary_admin_id, text=alert_text, parse_mode='HTML')\n",
        "                             except Exception:\n",
        "                                 pass\n",
        "\n",
        "                     card_text, card_markup = render_leaderboard_card(scans=scans, autopilot_status='AUTONOMOUS 60S CADENCE ACTIVE')\n",
        "                     if 'updater' in globals() and updater and updater.bot:\n",
        "                         try:\n",
        "                             updater.bot.send_message(chat_id=primary_admin_id, text=card_text, reply_markup=card_markup, parse_mode='HTML')\n",
        "                         except Exception as b_err:\n",
        "                             print(f'[!] Broadcast dispatch error: {b_err}')\n",
        "\n",
        "                     for item in (scans or []):\n",
        "                         s_edge = item.get('edge', 0)\n",
        "                         s_dir = item.get('direction', 'NEUTRAL')\n",
        "                         s_sym = item.get('symbol', '')\n",
        "                         if s_edge >= 75 and s_dir in ['BUY', 'SELL'] and s_sym not in active_syms:\n",
        "                             bot_obj = updater.bot if ('updater' in globals() and updater) else None\n",
        "                             execute_autonomous_signal(item, chat_id=primary_admin_id, bot_instance=bot_obj)\n",
        "                             break\n",
        "                 except Exception as loop_err:\n",
        "                     print(f'[!] Autonomous loop telemetry error: {loop_err}')\n",
    ]

    # Splice clean block directly
    lines = lines[:target_idx + 1] + clean_block + lines[end_idx:]
    text = "".join(lines)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("[+] Replacement applied cleanly without regex escaping errors.")
