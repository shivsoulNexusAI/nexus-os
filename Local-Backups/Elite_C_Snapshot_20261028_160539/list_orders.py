import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

TARGET_MAGIC = 999101


def show_orders_and_positions():
    if not mt5.initialize():
        print(f"❌ Failed to connect to MT5: {mt5.last_error()}")
        return

    # 1. Fetch Pending Orders (Buy Limit / Sell Limit)
    pending_orders = mt5.orders_get() or []
    algo_pending = [o for o in pending_orders if o.magic == TARGET_MAGIC]

    print("\n" + "=" * 80)
    print(f"⏳ PENDING ORDERS (Magic #{TARGET_MAGIC}) - Total: {len(algo_pending)}")
    print("=" * 80)
    if algo_pending:
        records = []
        for o in algo_pending:
            type_str = "BUY_LIMIT" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else "SELL_LIMIT"
            records.append({
                "Ticket": o.ticket,
                "Symbol": o.symbol,
                "Type": type_str,
                "Lots": o.volume_current,
                "Limit Price": o.price_open,
                "SL": o.sl,
                "TP": o.tp,
                "Placed At": datetime.fromtimestamp(o.time_setup).strftime("%Y-%m-%d %H:%M:%S")
            })
        print(pd.DataFrame(records).to_string(index=False))
    else:
        print("No pending orders waiting to be filled.")

    # 2. Fetch Active Open Positions (Filled Trades)
    positions = mt5.positions_get() or []
    algo_positions = [p for p in positions if p.magic == TARGET_MAGIC]

    print("\n" + "=" * 80)
    print(f"📈 ACTIVE MARKET POSITIONS (Magic #{TARGET_MAGIC}) - Total: {len(algo_positions)}")
    print("=" * 80)
    if algo_positions:
        pos_records = []
        for p in algo_positions:
            pos_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
            pos_records.append({
                "Ticket": p.ticket,
                "Symbol": p.symbol,
                "Type": pos_type,
                "Lots": p.volume,
                "Open Price": p.price_open,
                "Current Price": p.price_current,
                "SL": p.sl,
                "TP": p.tp,
                "Floating PnL ($)": round(p.profit, 2)
            })
        df_pos = pd.DataFrame(pos_records)
        print(df_pos.to_string(index=False))
        print("-" * 80)
        print(f"Total Floating PnL: ${df_pos['Floating PnL ($)'].sum():,.2f}")
    else:
        print("No active open positions currently in market.")

    mt5.shutdown()


if __name__ == "__main__":
    show_orders_and_positions()