from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")
code = p.read_text(encoding="utf-8")

if "from telegram_notifier_v43 import send_v43_alert" not in code:
    code = code.replace(
        "import MetaTrader5 as mt5",
        "import MetaTrader5 as mt5\nfrom telegram_notifier_v43 import send_v43_alert",
        1
    )

# EOD Runner Close Alert
old_eod = 'logging.info(f"[V4.3 EOD CLOSE] Closed surviving session runner {p.symbol} #{p.ticket} PnL=${p.profit:+.2f}")'
new_eod = '''logging.info(f"[V4.3 EOD CLOSE] Closed surviving session runner {p.symbol} #{p.ticket} PnL=${p.profit:+.2f}")
                        send_v43_alert(
                            f"🏁 <b>[V4.3 EOD RUNNER CLOSE]</b>\\n"
                            f"Asset: <b>{p.symbol}</b> (#{p.ticket})\\n"
                            f"Volume: {p.volume}L | Realized PnL: <b>${p.profit:+.2f}</b>"
                        )'''
if old_eod in code and "V4.3 EOD RUNNER CLOSE" not in code:
    code = code.replace(old_eod, new_eod, 1)

# Coiled Sell Armed Alert
old_sell = 'logging.info(f"[V4.3 COILED SELL ARMED] {sym} {lot}L SELL_STOP @ {round(box[\'sell_stop\'], info.digits)} | SL={sl_sell} | Delta={delta_pct:+.1f}% (#{res.order})")'
new_sell = '''logging.info(f"[V4.3 COILED SELL ARMED] {sym} {lot}L SELL_STOP @ {round(box['sell_stop'], info.digits)} | SL={sl_sell} | Delta={delta_pct:+.1f}% (#{res.order})")
                    send_v43_alert(
                        f"🔻 <b>[V4.3 COILED SELL ARMED]</b>\\n"
                        f"Asset: <b>{sym}</b> ({lot}L) | Ticket: #{res.order}\\n"
                        f"Entry Stop: <code>{round(box['sell_stop'], info.digits)}</code> | SL: <code>{sl_sell}</code>\\n"
                        f"Box Low: <code>{round(box['ref_low'], info.digits)}</code> | Delta: <b>{delta_pct:+.1f}%</b>"
                    )'''
if old_sell in code and "🔻 <b>[V4.3 COILED SELL ARMED]" not in code:
    code = code.replace(old_sell, new_sell, 1)

# Coiled Buy Armed Alert
old_buy = 'logging.info(f"[V4.3 COILED BUY ARMED] {sym} {lot}L BUY_STOP @ {round(box[\'buy_stop\'], info.digits)} | SL={sl_buy} | H1_BULL=True | Delta={delta_pct:+.1f}% (#{res.order})")'
new_buy = '''logging.info(f"[V4.3 COILED BUY ARMED] {sym} {lot}L BUY_STOP @ {round(box['buy_stop'], info.digits)} | SL={sl_buy} | H1_BULL=True | Delta={delta_pct:+.1f}% (#{res.order})")
                    send_v43_alert(
                        f"🚀 <b>[V4.3 COILED BUY ARMED]</b>\\n"
                        f"Asset: <b>{sym}</b> ({lot}L) | Ticket: #{res.order}\\n"
                        f"Entry Stop: <code>{round(box['buy_stop'], info.digits)}</code> | SL: <code>{sl_buy}</code>\\n"
                        f"H1 Trend: <b>BULLISH</b> | Delta: <b>{delta_pct:+.1f}%</b>"
                    )'''
if old_buy in code and "🚀 <b>[V4.3 COILED BUY ARMED]" not in code:
    code = code.replace(old_buy, new_buy, 1)

p.write_text(code, encoding="utf-8")
print("[OK] Wired Telegram alerts into nexus_multi_straddle_daemon.py")