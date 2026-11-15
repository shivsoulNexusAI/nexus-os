from pathlib import Path

gold_path = Path(r"C:\Quant-Nexus-Eng\gold_hft_straddle_daemon.py")
content = gold_path.read_text(encoding="utf-8", errors="ignore")

# 1. Calibrate re-center threshold to $2.50 (2500 points) instead of $0.10 (100 points)
content = content.replace(
    "elif abs(buy_stops[0].price_open - target_buy_price) > (100 * point):",
    "elif abs(buy_stops[0].price_open - target_buy_price) > (2500 * point):"
)
content = content.replace(
    "elif abs(sell_stops[0].price_open - target_sell_price) > (100 * point):",
    "elif abs(sell_stops[0].price_open - target_sell_price) > (2500 * point):"
)

# 2. Fix rounding from 2 to sym_info.digits (3 digits)
old_targets = """    target_buy_price = round(tick.ask + (STRADDLE_OFFSET_POINTS * point), 2)
    target_sell_price = round(tick.bid - (STRADDLE_OFFSET_POINTS * point), 2)"""

new_targets = """    digits = sym_info.digits
    target_buy_price = round(tick.ask + (STRADDLE_OFFSET_POINTS * point), digits)
    target_sell_price = round(tick.bid - (STRADDLE_OFFSET_POINTS * point), digits)"""

if old_targets in content:
    content = content.replace(old_targets, new_targets)

# 3. Fix SL/TP rounding in both buy and sell requests
content = content.replace('"sl": round(target_buy_price - (SL_POINTS * point), 2),', '"sl": round(target_buy_price - (SL_POINTS * point), digits),')
content = content.replace('"tp": round(target_buy_price + (TP_POINTS * point), 2),', '"tp": round(target_buy_price + (TP_POINTS * point), digits),')
content = content.replace('"sl": round(target_sell_price + (SL_POINTS * point), 2),', '"sl": round(target_sell_price + (SL_POINTS * point), digits),')
content = content.replace('"tp": round(target_sell_price - (TP_POINTS * point), 2),', '"tp": round(target_sell_price - (TP_POINTS * point), digits),')

# 4. Add error capture on order_send failures
old_buy_check = """        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log.info("Placed Buy Stop @ %.2f (ATR: $%.2f, CHOP: %.1f)", target_buy_price, atr, chop)"""

new_buy_check = """        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log.info("Placed Buy Stop @ %.*f (ATR: $%.2f, CHOP: %.1f)", digits, target_buy_price, atr, chop)
        else:
            err = res.comment if res else mt5.last_error()
            log.warning("Buy Stop Send Failed: %s (code %s)", err, getattr(res, 'retcode', 'None'))"""

if old_buy_check in content:
    content = content.replace(old_buy_check, new_buy_check)

old_sell_check = """        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log.info("Placed Sell Stop @ %.2f (ATR: $%.2f, CHOP: %.1f)", target_sell_price, atr, chop)"""

new_sell_check = """        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log.info("Placed Sell Stop @ %.*f (ATR: $%.2f, CHOP: %.1f)", digits, target_sell_price, atr, chop)
        else:
            err = res.comment if res else mt5.last_error()
            log.warning("Sell Stop Send Failed: %s (code %s)", err, getattr(res, 'retcode', 'None'))"""

if old_sell_check in content:
    content = content.replace(old_sell_check, new_sell_check)

gold_path.write_text(content, encoding="utf-8")
print("[+] Successfully polished gold_hft_straddle_daemon.py with 3-digit precision and resilient re-centering.")