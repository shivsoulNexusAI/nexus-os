import MetaTrader5 as mt5
import time

if mt5.initialize():
    now = time.time()
    deals = mt5.history_deals_get(now - 7200, now) or []
    header = "{:<12} | {:<8} | {:<5} | {:<6} | {:<12} | {}".format("DEAL", "SYMBOL", "TYPE", "VOL", "PROFIT", "COMMENT")
    print(header)
    print("-" * 75)
    closed_deals = [d for d in deals if d.entry == 1]
    if not closed_deals:
        print("[!] No exit deals recorded in the last 2 hours.")
    for d in closed_deals:
        dtype = "BUY" if d.type == 0 else "SELL"
        row = "#{:<11} | {:<8} | {:<5} | {:<6} | ${:+10.2f} | {}".format(d.ticket, d.symbol, dtype, d.volume, d.profit, d.comment)
        print(row)
    mt5.shutdown()
else:
    print("[-] Failed to initialize MT5.")
