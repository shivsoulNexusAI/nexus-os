import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

TARGET_MAGIC = 999101


def get_magic_positions():
    if not mt5.initialize():
        print(f"❌ Failed to initialize MT5: {mt5.last_error()}")
        return

    positions = mt5.positions_get()
    if positions is None:
        print(f"❌ Error fetching positions: {mt5.last_error()}")
        mt5.shutdown()
        return

    magic_positions = [p for p in positions if p.magic == TARGET_MAGIC]
    if not magic_positions:
        print(f"ℹ️ No active positions found with Magic Number #{TARGET_MAGIC}.")
        mt5.shutdown()
        return

    print(f"✅ Found {len(magic_positions)} active position(s) managed by Magic #{TARGET_MAGIC}:\n")

    records = []
    for pos in magic_positions:
        records.append({
            "Ticket": pos.ticket,
            "Symbol": pos.symbol,
            "Type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
            "Lots": pos.volume,
            "Open Price": pos.price_open,
            "Current": pos.price_current,
            "SL": pos.sl,
            "TP": pos.tp,
            "Profit ($)": round(pos.profit, 2),
            "Opened At": datetime.fromtimestamp(pos.time).strftime("%Y-%m-%d %H:%M:%S"),
            "Comment": pos.comment
        })

    df = pd.DataFrame(records)
    print(df.to_string(index=False))
    print("-" * 85)
    print(f"Total Floating PnL: ${df['Profit ($)'].sum():,.2f}")

    mt5.shutdown()


if __name__ == "__main__":
    get_magic_positions()