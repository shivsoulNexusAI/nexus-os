import MetaTrader5 as mt5
from datetime import datetime, timedelta

TERMINAL = r"C:/MT5_Quant_278017866/terminal64.exe"
if mt5.initialize(path=TERMINAL, portable=False):
    acc = mt5.account_info()
    now = datetime.now()
    deals = mt5.history_deals_get(now - timedelta(hours=24), now) or []
    closed = [d for d in deals if d.entry == 1]
    positions = mt5.positions_get() or []

    print("=" * 95)
    print(f"ACCOUNT #{acc.login} ({acc.server}) - 24-HOUR PERFORMANCE & CASHFLOW AUDIT")
    print(f"Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Margin Level: {acc.margin_level:.1f}%")
    print("=" * 95)

    if closed:
        print(f"\n[CLOSED DEALS TODAY: {len(closed)} EXITS]")
        print(f"{'Ticket':<12} | {'Symbol':<8} | {'Volume':<7} | {'Exit Price':<11} | {'Profit':<10} | {'Exit Time':<9} | {'Comment'}")
        print("-" * 95)
        total_pnl = 0.0
        wins = 0
        for d in closed:
            total_pnl += d.profit
            if d.profit > 0:
                wins += 1
            t_str = datetime.fromtimestamp(d.time).strftime("%H:%M:%S")
            print(f"#{d.ticket:<11} | {d.symbol:<8} | {d.volume:.2f}L   | {d.price:<11.5f} | ${d.profit:>+8.2f} | {t_str:<9} | {d.comment}")
        print("-" * 95)
        wr = (wins / len(closed)) * 100
        print(f"Total Closed PnL: ${total_pnl:>+8.2f} | Win Rate: {wr:.1f}% ({wins}/{len(closed)} trades)")
    else:
        print("\n[CLOSED DEALS TODAY: 0 exits recorded in the past 24 hours]")

    print(f"\n[CURRENT IN-FLIGHT POSITIONS: {len(positions)} ACTIVE]")
    if positions:
        print(f"{'Ticket':<12} | {'Symbol':<8} | {'Side':<5} | {'Volume':<7} | {'Open Price':<11} | {'Current':<11} | {'SL':<11} | {'PnL'}")
        print("-" * 95)
        for p in positions:
            side = "BUY" if p.type == 0 else "SELL"
            print(f"#{p.ticket:<11} | {p.symbol:<8} | {side:<5} | {p.volume:.2f}L   | {p.price_open:<11.5f} | {p.price_current:<11.5f} | {p.sl:<11.5f} | ${p.profit:>+7.2f}")
    else:
        print("No active open exposure. Capital is fully preserved in cash balance.")

    print("=" * 95)
    mt5.shutdown()
else:
    print("[-] MT5 Initialization failed.")