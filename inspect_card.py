import MetaTrader5 as mt5
import datetime

DAILY_MAX_LOSS_LIMIT = -300.00

def get_today_ledger():
    now = datetime.datetime.now()
    midnight_ts = datetime.datetime(now.year, now.month, now.day, 0, 0, 0).timestamp()
    now_ts = now.timestamp()
    
    deals = mt5.history_deals_get(midnight_ts, now_ts) or []
    closed = [d for d in deals if d.entry == 1 and (d.magic == 888999 or abs(d.profit) > 0.0001)]
    
    total_profit = sum(d.profit for d in closed)
    wins = len([d for d in closed if d.profit > 0])
    losses = len([d for d in closed if d.profit < 0])
    total_closed = len(closed)
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    
    tripped = total_profit <= DAILY_MAX_LOSS_LIMIT
    
    return {
        "closed_profit": total_profit,
        "wins": wins,
        "losses": losses,
        "total": total_closed,
        "win_rate": win_rate,
        "tripped": tripped
    }

def main():
    if not mt5.initialize():
        print("[-] Failed to initialize MT5")
        return

    acc = mt5.account_info()
    positions = mt5.positions_get() or []
    ledger = get_today_ledger()

    cb_status = "🚨 TRIPPED (LOCKED)" if ledger['tripped'] else "🛡️ ARMED (NORMAL)"

    print("=" * 60)
    print("🏛️ [NEXUS OMEGA INSTITUTIONAL TELEMETRY]")
    print(f"Account: #{acc.login} | Equity: ${acc.equity:,.2f} | Balance: ${acc.balance:,.2f}")
    print(f"Margin Level: {acc.margin_level:,.1f}% | Floating PnL: ${acc.profit:+,.2f}")
    print(f"Daily Circuit Breaker: {cb_status} [Limit: ${DAILY_MAX_LOSS_LIMIT:,.2f}]")
    print("-" * 60)
    print("📊 TODAY'S REALIZED LEDGER:")
    print(f"  • Realized PnL: ${ledger['closed_profit']:+,.2f} | Win Rate: {ledger['win_rate']:.1f}%")
    print(f"  • Scorecard   : {ledger['wins']} Wins / {ledger['losses']} Losses ({ledger['total']} Closed Deals)")
    print("-" * 60)
    print("📡 ICT MULTI-ASSET RADAR:")
    
    monitored_syms = ["USDJPY", "BTCUSD", "EURUSD", "XAUUSD", "GBPUSD"]
    pos_map = {p.symbol: p for p in positions}

    for s in monitored_syms:
        if s in pos_map:
            p = pos_map[s]
            side = "BUY" if p.type == 0 else "SELL"
            be_tag = "🛡️ BE | " if abs(p.sl - p.price_open) < 0.001 else ""
            print(f"- {s:<7}: [{side} {p.volume}L | {be_tag}PnL: ${p.profit:+,.2f}]")
        else:
            print(f"- {s:<7}: [FLAT | STANDBY]")

    print("-" * 60)
    print(f"Active Monitored Positions: {len(positions)}")
    for p in positions:
        side = "BUY" if p.type == 0 else "SELL"
        if p.sl > 0 and abs(p.price_open - p.sl) < 0.001:
            r_str = "🛡️ BE"
        else:
            risk_dist = abs(p.price_open - p.sl) if p.sl > 0 else 0.0
            if risk_dist > 0:
                fl_dist = (p.price_current - p.price_open) if p.type == 0 else (p.price_open - p.price_current)
                r = fl_dist / risk_dist
                r_str = f"{r:+.1f}R"
            else:
                r_str = "No SL"
        print(f"  #{p.ticket} | {p.symbol} {side} {p.volume}L | Open: {p.price_open} | SL: {p.sl} | Cur: {p.price_current} | {r_str} (${p.profit:+,.2f})")
    print("=" * 60)
    mt5.shutdown()

if __name__ == "__main__":
    main()
