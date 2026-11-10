from nexus_logging_guard import get_rotating_logger
"""
QUANTNEXUS WEEKLY ALPHA REPORTER (v1.0 Production)
Audits MT5 rolling 7-day trade history, calculates institutional performance
and risk metrics (Sharpe, Sortino, Profit Factor, DD), and broadcasts to Telegram.
"""
import os
import sys
import math
import logging
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_telegram import send_alert

LOG_PATH = r"C:\Quant-Nexus-Eng\weekly_alpha_reporter.log"
logger = get_rotating_logger("WeeklyAlphaReporter", "weekly_alpha_reporter.log")

MT5_PATH = r"C:\MT5_HFT_278041671\terminal64.exe"
DAYS_LOOKBACK = 7

def compute_metrics(deals):
    if not deals:
        return None

    # Filter closed out / inout deals with realized profit
    closed = [d for d in deals if d.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT]]
    if not closed:
        return None

    net_pnls = [round(d.profit + d.swap + d.commission, 2) for d in closed]
    total_trades = len(net_pnls)
    gross_profit = sum(p for p in net_pnls if p > 0)
    gross_loss = abs(sum(p for p in net_pnls if p < 0))
    net_profit = sum(net_pnls)

    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p < 0]
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    # Daily Return Distribution for Sharpe & Sortino (Annualized with factor sqrt(252))
    # Group trades by date
    daily_returns = {}
    for d in closed:
        trade_date = datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%Y-%m-%d")
        pnl = d.profit + d.swap + d.commission
        daily_returns[trade_date] = daily_returns.get(trade_date, 0.0) + pnl

    returns_list = list(daily_returns.values())
    n_days = max(1, len(returns_list))
    mean_return = sum(returns_list) / n_days

    # Standard Deviation of Daily Returns
    variance = sum((r - mean_return) ** 2 for r in returns_list) / n_days if n_days > 1 else 0.0
    stdev = math.sqrt(variance)

    # Downside Deviation for Sortino (penalizes only negative daily returns)
    downside_variance = sum((min(0.0, r)) ** 2 for r in returns_list) / n_days
    downside_stdev = math.sqrt(downside_variance)

    # Annualized Sharpe & Sortino (assuming 0 risk-free rate)
    sharpe = (mean_return / stdev * math.sqrt(252)) if stdev > 0 else 0.0
    sortino = (mean_return / downside_stdev * math.sqrt(252)) if downside_stdev > 0 else 0.0

    # Running Equity Curve & Peak Drawdown
    peak = 0.0
    max_dd = 0.0
    running_eq = 0.0
    for p in net_pnls:
        running_eq += p
        if running_eq > peak:
            peak = running_eq
        dd = peak - running_eq
        if dd > max_dd:
            max_dd = dd

    # Breakdown by Symbol
    symbols = {}
    for d in closed:
        sym = d.symbol
        pnl = d.profit + d.swap + d.commission
        if sym not in symbols:
            symbols[sym] = {"trades": 0, "wins": 0, "pnl": 0.0}
        symbols[sym]["trades"] += 1
        symbols[sym]["pnl"] += pnl
        if pnl > 0:
            symbols[sym]["wins"] += 1

    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "net_profit": net_profit,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": max_dd,
        "symbols": symbols
    }

def generate_weekly_report():
    logger.info("Starting Weekly Alpha Report generation...")
    if not mt5.initialize(path=MT5_PATH):
        logger.error(f"MT5 failed to initialize at {MT5_PATH}")
        return

    now_utc = datetime.now(timezone.utc)
    from_date = now_utc - timedelta(days=DAYS_LOOKBACK)
    to_date = now_utc + timedelta(minutes=5)

    deals = mt5.history_deals_get(from_date, to_date)
    acc = mt5.account_info()
    mt5.shutdown()

    if not deals:
        logger.info("No closed deals found in rolling 7-day period.")
        return

    metrics = compute_metrics(deals)
    if not metrics:
        logger.info("No realized round-turn deals to evaluate.")
        return

    # Build Telegram Digest
    pnl_badge = "🟢" if metrics["net_profit"] >= 0 else "🔴"
    
    # Format per-symbol attribution
    sym_lines = []
    for sym, sdata in metrics["symbols"].items():
        wr = (sdata["wins"] / sdata["trades"] * 100) if sdata["trades"] > 0 else 0
        sym_lines.append(f"  • <code>{sym:<8}</code>: {sdata['trades']} trades | WR: {wr:.0f}% | PnL: ${sdata['pnl']:+,.2f}")
    symbols_text = "\n".join(sym_lines)

    report_msg = (
        f"📊 <b>[QUANTNEXUS ALPHA REPORT]</b> Rolling 7-Day Performance\n"
        f"• Range: <code>{from_date.strftime('%Y-%m-%d')} -> {now_utc.strftime('%Y-%m-%d')}</code>\n\n"
        f"<b>Key Risk & Profit Metrics:</b>\n"
        f"• Net Realized PnL: <b>${metrics['net_profit']:+,.2f}</b> {pnl_badge}\n"
        f"• Total Trades: <code>{metrics['total_trades']}</code> (Win Rate: <b>{metrics['win_rate']:.1f}%</b>)\n"
        f"• Profit Factor: <b>{metrics['profit_factor']:.2f}</b>\n"
        f"• Sharpe Ratio: <code>{metrics['sharpe']:.2f}</code> | Sortino: <code>{metrics['sortino']:.2f}</code>\n"
        f"• Max Trade Drawdown: <code>${metrics['max_dd']:,.2f}</code>\n"
        f"• Avg Win: <code>${metrics['avg_win']:,.2f}</code> | Avg Loss: <code>${metrics['avg_loss']:,.2f}</code>\n\n"
        f"<b>Symbol Attribution:</b>\n{symbols_text}\n\n"
        f"• Account Balance: <code>${getattr(acc, 'balance', 0.0):,.2f}</code> | Equity: <code>${getattr(acc, 'equity', 0.0):,.2f}</code>"
    )

    logger.info("Sending weekly performance digest to Telegram...")
    send_alert("quant_alert_bot", report_msg)
    logger.info("Weekly Alpha Report generated and dispatched successfully.")

if __name__ == "__main__":
    generate_weekly_report()
