import csv
import os
import datetime

JOURNAL_FILE = "trade_journal.csv"
FIELDNAMES = [
    "ticket", "symbol", "direction", "lots", "open_time", "close_time",
    "open_price", "close_price", "initial_sl", "tp", "risk_pips",
    "realized_profit_usd", "r_multiple", "pd_model", "exit_reason"
]

def initialize_journal():
    if not os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()

def log_trade_close(ticket, symbol, direction, lots, open_time, close_time,
                    open_price, close_price, initial_sl, tp, profit_usd,
                    pd_model="ICT_CONFLUENCE", exit_reason="TARGET_OR_TRAIL"):
    """
    Appends a closed trade to the institutional journal and calculates realized R-multiple.
    """
    initialize_journal()

    # Calculate initial risk distance (1R in price points)
    risk_dist = abs(open_price - initial_sl) if initial_sl else 0.0001
    if risk_dist <= 0:
        risk_dist = 0.0001

    gain_dist = (close_price - open_price) if direction.upper() == "BUY" else (open_price - close_price)
    r_mult = round(gain_dist / risk_dist, 2)

    row = {
        "ticket": ticket,
        "symbol": symbol,
        "direction": direction,
        "lots": round(lots, 2),
        "open_time": open_time,
        "close_time": close_time,
        "open_price": round(open_price, 5),
        "close_price": round(close_price, 5),
        "initial_sl": round(initial_sl, 5) if initial_sl else 0.0,
        "tp": round(tp, 5) if tp else 0.0,
        "risk_pips": round(risk_dist, 5),
        "realized_profit_usd": round(profit_usd, 2),
        "r_multiple": r_mult,
        "pd_model": pd_model,
        "exit_reason": exit_reason
    }

    try:
        with open(JOURNAL_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerow(row)
        return row
    except Exception:
        return None

def compute_session_metrics():
    """
    Reads the CSV and calculates institutional statistics:
    Win Rate, Total R-Multiple, Expectancy, and Profit Factor.
    """
    if not os.path.exists(JOURNAL_FILE):
        return None

    trades = []
    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)

    if not trades:
        return None

    total_trades = len(trades)
    wins = [float(t["realized_profit_usd"]) for t in trades if float(t["realized_profit_usd"]) > 0]
    losses = [abs(float(t["realized_profit_usd"])) for t in trades if float(t["realized_profit_usd"]) < 0]
    r_multiples = [float(t["r_multiple"]) for t in trades]

    win_count = len(wins)
    win_rate = (win_count / total_trades) * 100 if total_trades else 0
    total_gain = sum(wins)
    total_loss = sum(losses)
    pf = (total_gain / total_loss) if total_loss > 0 else (999.0 if total_gain > 0 else 0.0)
    net_r = sum(r_multiples)
    avg_r = net_r / total_trades if total_trades else 0

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(pf, 2),
        "net_r": round(net_r, 2),
        "avg_r": round(avg_r, 2),
        "net_pnl": round(total_gain - total_loss, 2)
    }
