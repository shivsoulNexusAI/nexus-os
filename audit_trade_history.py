import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
LOGIN = 278029146
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"

if not mt5.initialize(path=PATH, login=LOGIN, password=PASSWORD, server=SERVER, portable=True):
    print(f"[!] MT5 Initialization Failed: {mt5.last_error()}")
    quit()

acc = mt5.account_info()
print("=" * 85)
print(f"QUANT NEXUS DEEP DELTA AUDIT | DESK ACCOUNT: {acc.login} ({acc.server})")
print(f"Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Free Margin: ${acc.margin_free:,.2f} | Leverage: 1:{acc.leverage}")
print("=" * 85)

# 1. Closed Historical Deals Audit
from_date = datetime.now(timezone.utc) - timedelta(days=7)
deals = mt5.history_deals_get(from_date, datetime.now(timezone.utc))

print("\n--- [HISTORICAL CLOSED EXECUTIONS & DELTAS] ---")
if not deals:
    print("No closed deals found in the specified lookback window.")
else:
    total_pnl = 0.0
    total_comm = 0.0
    wins, losses = 0, 0
    for d in deals:
        if d.entry == mt5.DEAL_ENTRY_OUT:
            total_pnl += d.profit
            total_comm += (d.commission + d.fee + d.swap)
            side = "EXIT_BUY" if d.type == 0 else "EXIT_SELL"
            outcome = "WIN" if d.profit >= 0 else "LOSS"
            if d.profit >= 0: wins += 1
            else: losses += 1
            print(f"Ticket #{d.ticket} | {d.symbol:<7} {side} {d.volume:.2f}L | Exit: {d.price} | PnL: ${d.profit:+.2f} ({outcome}) | Fee: ${d.commission:.2f}")

    total_closed = wins + losses
    win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0
    print(f"\nClosed Realized PnL: ${total_pnl:+.2f} | Friction/Fees: ${total_comm:+.2f} | Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)")

# 2. Live Floating Fleet Deep Delta & Stop Loss Proximity Audit
positions = mt5.positions_get()
print("\n--- [LIVE OPEN FLEET & STOP LOSS PROXIMITY DELTAS] ---")
if not positions:
    print("No active open positions. Capital is 100% idle and fully protected.")
else:
    now_utc = datetime.now(timezone.utc)
    for p in positions:
        side = "BUY" if p.type == 0 else "SELL"
        open_time = datetime.fromtimestamp(p.time, timezone.utc)
        elapsed_min = (now_utc - open_time).total_seconds() / 60.0
        kronos_remaining = max(0.0, 60.0 - elapsed_min)

        # Distance deltas
        cur_price = p.price_current
        sl_price = p.sl
        tp_price = p.tp

        if side == "BUY":
            sl_delta_pts = (cur_price - sl_price) if sl_price > 0 else 0.0
            tp_delta_pts = (tp_price - cur_price) if tp_price > 0 else 0.0
        else:
            sl_delta_pts = (sl_price - cur_price) if sl_price > 0 else 0.0
            tp_delta_pts = (cur_price - tp_price) if tp_price > 0 else 0.0

        print(f"Position Ticket #{p.ticket} | {p.symbol} ({side} {p.volume:.2f}L)")
        print(f"  Entry: {p.price_open} | Current: {cur_price} | Floating PnL: ${p.profit:+.2f}")
        print(f"  Hard SL: {sl_price} | Dist to SL: {sl_delta_pts:.4f} pts | Hard TP: {tp_price} | Dist to TP: {tp_delta_pts:.4f} pts")
        print(f"  Kronos Age: {elapsed_min:.1f}m / 60.0m limit ({kronos_remaining:.1f}m until temporal exit)")

print("=" * 85)
mt5.shutdown()
