import MetaTrader5 as mt5

def protect_fleet_profits():
    """
    Automated Profit Protection Engine:
    1. Moves SL to Breakeven once in initial profit.
    2. Locks in tiered profits as the trade extends.
    """
    positions = mt5.positions_get()
    if not positions:
        return

    for pos in positions:
        ticket = pos.ticket
        symbol = pos.symbol
        pos_type = pos.type  # 0 = BUY, 1 = SELL
        open_price = pos.price_open
        current_price = pos.price_current
        sl = pos.sl
        tp = pos.tp
        profit = pos.profit

        # Request symbol specifications for point calculation
        info = mt5.symbol_info(symbol)
        if not info:
            continue
        point = info.point

        # ----------------------------------------------------
        # 1. BREAKEVEN PROTECTION (Triggered at +$50.00 profit)
        # ----------------------------------------------------
        if profit >= 50.0:
            if pos_type == 1:  # SELL Position
                be_price = round(open_price - (10 * point), info.digits)
                if sl == 0.0 or sl > open_price:
                    modify_sl(ticket, symbol, be_price, tp)
                    print(f"[{symbol}] Ticket #{ticket} Locked to BREAKEVEN @ {be_price}")

            elif pos_type == 0:  # BUY Position
                be_price = round(open_price + (10 * point), info.digits)
                if sl == 0.0 or sl < open_price:
                    modify_sl(ticket, symbol, be_price, tp)
                    print(f"[{symbol}] Ticket #{ticket} Locked to BREAKEVEN @ {be_price}")

        # ----------------------------------------------------
        # 2. TIERED PROFIT RATCHET (Lock 50% of gains over $100)
        # ----------------------------------------------------
        if profit >= 100.0:
            # Calculate 50% locked profit distance in price
            if pos_type == 1:  # SELL
                # Price moved down from open
                locked_target = round(open_price - ((open_price - current_price) * 0.5), info.digits)
                if sl > locked_target:
                    modify_sl(ticket, symbol, locked_target, tp)
                    print(f"[{symbol}] Ticket #{ticket} Trailing Profit Locked @ {locked_target}")

            elif pos_type == 0:  # BUY
                # Price moved up from open
                locked_target = round(open_price + ((current_price - open_price) * 0.5), info.digits)
                if sl < locked_target:
                    modify_sl(ticket, symbol, locked_target, tp)
                    print(f"[{symbol}] Ticket #{ticket} Trailing Profit Locked @ {locked_target}")

def modify_sl(ticket, symbol, new_sl, tp):
    """Sends modification request to MT5."""
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": symbol,
        "sl": new_sl,
        "tp": tp
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Modify SL failed for #{ticket}: {result.comment}")
