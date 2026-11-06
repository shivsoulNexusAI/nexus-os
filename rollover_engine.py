import os
import json
import datetime
import MetaTrader5 as mt5

REPORTS_DIR = "reports"

def check_and_execute_daily_rollover(last_rollover_date_str: str) -> tuple[str, bool]:
    """
    Checks if UTC midnight has passed since last rollover.
    Archives yesterday's ledger stats to reports/ and clears the circuit breaker lock.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    if last_rollover_date_str == today_str:
        return last_rollover_date_str, False

    # Midnight UTC Rollover Triggered
    if not os.path.exists(REPORTS_DIR):
        os.makedirs(REPORTS_DIR, exist_ok=True)

    # Pull yesterday's deals if MT5 connected
    deals_data = []
    tot_pnl = 0.0
    wins, losses = 0, 0

    if mt5.initialize():
        yesterday_midnight = (now_utc - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today_midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        deals = mt5.history_deals_get(yesterday_midnight, today_midnight) or []
        closed = [d for d in deals if d.entry == 1 and (d.magic == 888999 or abs(d.profit) > 0.0001)]
        tot_pnl = sum(d.profit for d in closed)
        wins = len([d for d in closed if d.profit > 0])
        losses = len([d for d in closed if d.profit < 0])
        deals_data = [{"ticket": d.ticket, "symbol": d.symbol, "profit": d.profit, "time": d.time} for d in closed]

    report = {
        "date": (now_utc - datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
        "total_realized_pnl": round(tot_pnl, 2),
        "closed_deals": len(deals_data),
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / len(deals_data) * 100) if deals_data else 0.0, 1),
        "deals": deals_data,
        "archived_at_utc": now_utc.isoformat()
    }

    report_path = os.path.join(REPORTS_DIR, f"daily_ledger_{report['date']}.json")
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)

    print(f"\n[🔄 00:00 UTC ROLLOVER] Archived ledger to {report_path}. Resetting Circuit Breaker to ARMED.")
    return today_str, True

if __name__ == "__main__":
    test_date, triggered = check_and_execute_daily_rollover("2026-01-01")
    print(f"Test Run: Date={test_date} | Triggered={triggered}")
