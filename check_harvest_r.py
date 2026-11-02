import MetaTrader5 as mt5

def check_harvest_r():
    if not mt5.initialize():
        print("[-] MT5 Init failed")
        return

    positions = mt5.positions_get() or []
    print("TICKET        | SYMBOL   | TYPE  | VOL    | CURRENT R  | HARVEST STATUS")
    print("-" * 75)
    
    if not positions:
        print("No open positions found.")
        mt5.shutdown()
        return

    for p in positions:
        sym = p.symbol
        risk_dist = 0.0020
        if "JPY" in sym: risk_dist = 0.200
        elif "XAU" in sym: risk_dist = 5.00
        elif "BTC" in sym: risk_dist = 150.0

        p_type = "BUY" if p.type == 0 else "SELL"
        cur_dist = (p.price_current - p.price_open) if p.type == 0 else (p.price_open - p.price_current)
        cur_r = cur_dist / risk_dist
        dist_to_harvest = 1.5 - cur_r

        status = "READY FOR HARVEST 🚀" if dist_to_harvest <= 0 else f"{dist_to_harvest:+.2f}R to Harvest"
        print(f"#{p.ticket:<12} | {sym:<8} | {p_type:<5} | {p.volume:<6} | {cur_r:+7.2f}R   | {status}")
        
    mt5.shutdown()

if __name__ == "__main__":
    check_harvest_r()
