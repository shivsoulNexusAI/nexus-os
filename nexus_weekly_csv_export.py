import os
import csv
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def export_weekly_trade_attribution_csv(sleeves_dict, output_dir=r"C:\Quant-Nexus-Eng\reports"):
    """
    Compiles trade history across all tripartite sleeves, aggregates performance
    and net R attribution by strategy, and exports a timestamped CSV report.
    """
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_filename = os.path.join(output_dir, f"nexus_weekly_attribution_{ts}.csv")

    rows = []
    headers = ["Sleeve", "Symbol", "Ticket", "Type", "Volume", "OpenTime", "CloseTime", "Profit", "NetR", "StrategyTag"]

    for sleeve_name, cfg in sleeves_dict.items():
        if mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"]):
            from_date = datetime.now(timezone.utc) - timedelta(days=7)
            deals = mt5.history_deals_get(from_date, datetime.now(timezone.utc))
            
            if deals is not None:
                for deal in deals:
                    if deal.entry == mt5.DEAL_ENTRY_OUT:
                        profit = deal.profit + deal.commission + deal.swap
                        net_r = round(profit / max(1.0, abs(deal.volume * 10.0)), 2)
                        strat_tag = "OB+IFVG+VP" if "OB" in str(deal.comment) else "SWEEP_VP"
                        
                        rows.append({
                            "Sleeve": sleeve_name,
                            "Symbol": deal.symbol,
                            "Ticket": deal.position_id,
                            "Type": "BUY" if deal.type == mt5.DEAL_TYPE_BUY else "SELL",
                            "Volume": deal.volume,
                            "OpenTime": datetime.fromtimestamp(deal.time, tz=timezone.utc).strftime("%Y%m%d_%H%M%S"),
                            "CloseTime": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
                            "Profit": round(profit, 2),
                            "NetR": net_r,
                            "StrategyTag": strat_tag
                        })
            mt5.shutdown()

    with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Exported {len(rows)} trade records to {csv_filename}")
    return csv_filename

if __name__ == "__main__":
    from nexus_ship_core import SLEEVES
    export_weekly_trade_attribution_csv(SLEEVES)
