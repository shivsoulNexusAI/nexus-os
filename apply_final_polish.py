from pathlib import Path
import re

path = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")
content = path.read_text(encoding="utf-8", errors="ignore")

# 1. Enforce 0.02 base volume for partial harvests
old_lot_pattern = r"lot\s*=\s*info\.volume_min"
new_lot_code = "lot = max(info.volume_min * 2.0, 0.02) if info.volume_min <= 0.01 else info.volume_min"
content = re.sub(old_lot_pattern, new_lot_code, content)

# 2. Enforce 60-minute broker order expiration
old_buy_req = '''req_buy = {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY_STOP,
                    "price": buy_stop,
                    "sl": buy_sl,
                    "tp": buy_tp,'''

new_buy_req = '''req_buy = {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY_STOP,
                    "price": buy_stop,
                    "sl": buy_sl,
                    "tp": buy_tp,
                    "type_time": mt5.ORDER_TIME_SPECIFIED,
                    "expiration": int(time.time()) + 3600,'''

if old_buy_req in content:
    content = content.replace(old_buy_req, new_buy_req)

old_sell_req = '''req_sell = {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_SELL_STOP,
                    "price": sell_stop,
                    "sl": sell_sl,
                    "tp": sell_tp,'''

new_sell_req = '''req_sell = {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_SELL_STOP,
                    "price": sell_stop,
                    "sl": sell_sl,
                    "tp": sell_tp,
                    "type_time": mt5.ORDER_TIME_SPECIFIED,
                    "expiration": int(time.time()) + 3600,'''

if old_sell_req in content:
    content = content.replace(old_sell_req, new_sell_req)

path.write_text(content, encoding="utf-8")
print("[+] nexus_multi_straddle_daemon.py patched with 0.02L harvestable sizing and 60-min TTL.")