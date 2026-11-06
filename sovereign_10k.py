import os
import time
import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5

JOURNAL_FILE = "trade_journal.csv"
RISK_UNIT_USD = 25.0  # Base institutional risk unit for R normalization

def sync_closed_deals_to_journal():
    """Queries broker history for any deals not yet in trade_journal.csv and appends them."""
    try:
        from_time = datetime.now() - timedelta(days=3)
        deals = mt5.history_deals_get(from_time, datetime.now())
        if not deals:
            return

        existing_deals = set()
        if os.path.exists(JOURNAL_FILE):
            try:
                df_curr = pd.read_csv(JOURNAL_FILE)
                if not df_curr.empty and 'deal_ticket' in df_curr.columns:
                    existing_deals = set(df_curr['deal_ticket'].astype(int).tolist())
            except Exception:
                pass

        new_entries = []
        for d in deals:
            # Entry 1 indicates out/exit deal, profit != 0 indicates settled outcome
            if d.profit != 0 and d.ticket not in existing_deals:
                new_entries.append({
                    "deal_ticket": int(d.ticket),
                    "order_ticket": int(d.order),
                    "symbol": d.symbol,
                    "type": "BUY" if d.type == 0 else "SELL",
                    "volume": float(d.volume),
                    "entry_price": float(d.price),
                    "realized_profit_usd": round(float(d.profit), 2),
                    "r_multiple": round(float(d.profit) / RISK_UNIT_USD, 2),
                    "close_time": datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S")
                })

        if new_entries:
            df_new = pd.DataFrame(new_entries)
            if os.path.exists(JOURNAL_FILE):
                df_new.to_csv(JOURNAL_FILE, mode='a', header=False, index=False)
            else:
                df_new.to_csv(JOURNAL_FILE, mode='w', header=True, index=False)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [AUTO-JOURNAL] Synced {len(new_entries)} closed deal(s) to {JOURNAL_FILE}")
    except Exception as e:
        print(f"[AUTO-JOURNAL ERROR] {e}")

def run_sentinel_daemon():
    if not mt5.initialize():
        print("[-] Failed to initialize MT5")
        return

    print("=" * 70)
    print("⚡ SENTINEL SOVEREIGN 10K DAEMON WITH AUTONOMOUS JOURNAL SYNC")
    print("=" * 70)

    last_journal_sync = 0

    while True:
        try:
            positions = mt5.positions_get()
            now_ts = time.time()

            # 1. Manage Trailing Stops & Breakeven logic
            if positions:
                for p in positions:
                    direction = 0 if p.type == mt5.ORDER_TYPE_BUY else 1
                    risk = abs(p.price_open - p.sl) if p.sl else 0.0001
                    dist = (p.price_current - p.price_open) if direction == 0 else (p.price_open - p.price_current)
                    cur_r = dist / (risk if risk > 0 else 0.0001)

                    # Ratchet to Breakeven (+0.0R) when trade reaches >= +1.0R
                    if cur_r >= 1.0:
                        needs_be = False
                        if direction == 0 and (p.sl is None or p.sl < p.price_open):
                            needs_be = True
                        elif direction == 1 and (p.sl is None or p.sl > p.price_open):
                            needs_be = True

                        if needs_be:
                            req = {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "position": p.ticket,
                                "sl": p.price_open,
                                "tp": p.tp
                            }
                            res = mt5.order_send(req)
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Locked Breakeven on #{p.ticket} ({p.symbol}) at {p.price_open}")

            # 2. Synchronize closed deals every 10 seconds
            if now_ts - last_journal_sync >= 10:
                sync_closed_deals_to_journal()
                last_journal_sync = now_ts

            time.sleep(3)

        except Exception as err:
            print(f"[DAEMON ERROR] {err}")
            time.sleep(5)

if __name__ == "__main__":
    run_sentinel_daemon()
