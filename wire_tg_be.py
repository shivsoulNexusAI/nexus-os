from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\breakeven_engine.py")
code = p.read_text(encoding="utf-8")

if "from telegram_notifier_v43 import send_v43_alert" not in code:
    code = code.replace(
        "import MetaTrader5 as mt5",
        "import MetaTrader5 as mt5\nfrom telegram_notifier_v43 import send_v43_alert",
        1
    )

old_t1 = 'logging.info(f"[TIER 1 +0.85R BE LOCK] {p.symbol} #{p.ticket} SL -> {be_sl}")'
new_t1 = '''logging.info(f"[TIER 1 +0.85R BE LOCK] {p.symbol} #{p.ticket} SL -> {be_sl}")
                    send_v43_alert(
                        f"🛡️ <b>[V4.3 TIER 1: +0.85R BE LOCK]</b>\\n"
                        f"Asset: <b>{p.symbol}</b> (#{p.ticket})\\n"
                        f"Protected SL: <code>{be_sl}</code> (+0.12R cushion)"
                    )'''
if old_t1 in code and "V4.3 TIER 1: +0.85R BE LOCK" not in code:
    code = code.replace(old_t1, new_t1, 1)

old_t2 = 'logging.info(f"[TIER 2 +1.60R HARVEST] {p.symbol} #{p.ticket} banked {close_vol}L | Uncapped Runner Floor SL -> {ratch_sl}")'
new_t2 = '''logging.info(f"[TIER 2 +1.60R HARVEST] {p.symbol} #{p.ticket} banked {close_vol}L | Uncapped Runner Floor SL -> {ratch_sl}")
                send_v43_alert(
                    f"💰 <b>[V4.3 TIER 2: +1.60R 50% HARVEST]</b>\\n"
                    f"Asset: <b>{p.symbol}</b> (#{p.ticket})\\n"
                    f"Banked: <b>{close_vol}L</b> @ <code>{cur_price}</code>\\n"
                    f"Uncapped Runner Floor SL: <code>{ratch_sl}</code> (+1.00R locked)"
                )'''
if old_t2 in code and "V4.3 TIER 2: +1.60R 50% HARVEST" not in code:
    code = code.replace(old_t2, new_t2, 1)

p.write_text(code, encoding="utf-8")
print("[OK] Wired Telegram alerts into breakeven_engine.py")