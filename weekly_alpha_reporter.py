"""
QUANTNEXUS WEEKLY ALPHA REPORTER (v1.1 Production - 4-Terminal Cluster T1-T4)
Audits rolling 7-day realized trade history across all four MT5 terminals
(TERM_QUANT_278061453, TERM_HFT_278041671, TERM_PENDING_278041169, TERM_SOVEREIGN_278071462),
computes institutional risk/return metrics (Sharpe, Sortino, Profit Factor, DD), and broadcasts to Telegram.
"""
import os
import gc
import sys
import math
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_logging_guard import get_rotating_logger
from nexus_telegram import send_alert

logger = get_rotating_logger("WeeklyAlphaReporter", "weekly_alpha_reporter.log")

GODMODE_TOKEN = "8500432698:AAFLDz1nN_JeSMo2HBNx2gujV7tSlMfQGGg"
GODMODE_CHAT_ID = "5279761713"
DAYS_LOOKBACK = 7

TERMINAL_CONFIG = [
    {"id": "T1_QUANT_278061453", "path": r"C:\MT5_Quant_278061453\terminal64.exe", "portable": False},
    {"id": "T2_HFT_278041671", "path": r"C:\MT5_HFT_278041671\terminal64.exe", "portable": False},
    {"id": "T3_PENDING_278041169", "path": r"C:\MT5_Pending_278041169\terminal64.exe", "portable": False},
    {"id": "T4_SOVEREIGN_278071462", "path": r"C:\MT5_Sovereign_T4\terminal64.exe", "portable": True},
]


def send_godmode_alert(text: str):
    try:
        url = f"https://api.telegram.org/bot{GODMODE_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": GODMODE_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception as e:
        logger.warning(f"GODMODEAI2050_bot dispatch warning: {e}")


def compute_metrics(closed_records):
    if not closed_records:
        return None

    closed_records.sort(key=lambda x: x["time"])
    net_pnls = [round(r["net_pnl"], 2) for r in closed_records]
    total_trades = len(net_pnls)
    gross_profit = sum(p for p in net_pnls if p > 0)
    gross_loss = abs(sum(p for p in net_pnls if p < 0))
    net_profit = sum(net_pnls)

    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p < 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    daily_returns = {}
    for r in closed_records:
        trade_date = datetime.fromtimestamp(r["time"], tz=timezone.utc).strftime("%Y-%m-%d")
        daily_returns[trade_date] = daily_returns.get(trade_date, 0.0) + r["net_pnl"]

    returns_list = list(daily_returns.values())
    n_days = max(1, len(returns_list))
    mean_return = sum(returns_list) / n_days

    variance = sum((v - mean_return) ** 2 for v in returns_list) / n_days if n_days > 1 else 0.0
    stdev = math.sqrt(variance)

    downside_variance = sum((min(0.0, v)) ** 2 for v in returns_list) / n_days
    downside_stdev = math.sqrt(downside_variance)

    sharpe = (mean_return / stdev * math.sqrt(252)) if stdev > 0 else 0.0
    sortino = (mean_return / downside_stdev * math.sqrt(252)) if downside_stdev > 0 else 0.0

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

    symbols = {}
    for r in closed_records:
        sym = r["symbol"]
        pnl = r["net_pnl"]
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
        "symbols": symbols,
    }


def generate_weekly_report(broadcast: bool = True):
    logger.info("Starting 4-Node Cluster Weekly Alpha Report generation...")
    now_utc = datetime.now(timezone.utc)
    from_date = now_utc - timedelta(days=DAYS_LOOKBACK)
    to_date = now_utc + timedelta(minutes=5)

    all_closed = []
    node_summaries = []
    total_balance = 0.0
    total_equity = 0.0

    for node in TERMINAL_CONFIG:
        nid = node["id"]
        path = node["path"]
        if not os.path.exists(path):
            node_summaries.append(f"  ? <code>{nid}</code>: OFFLINE")
            continue

        init_ok = mt5.initialize(path=path, portable=True) if node["portable"] else mt5.initialize(path=path)
        if not init_ok:
            logger.warning(f"MT5 failed to initialize at {path}: {mt5.last_error()}")
            node_summaries.append(f"  ? <code>{nid}</code>: INIT_ERR")
            continue

        deals = mt5.history_deals_get(from_date, to_date) or []
        acc = mt5.account_info()
        bal = float(getattr(acc, "balance", 0.0))
        eq = float(getattr(acc, "equity", 0.0))
        total_balance += bal
        total_equity += eq

        node_closed = [
            {
                "node": nid,
                "time": int(d.time),
                "symbol": d.symbol,
                "net_pnl": float(d.profit + d.swap + d.commission),
            }
            for d in deals
            if d.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT]
        ]
        all_closed.extend(node_closed)

        n_pnl = sum(r["net_pnl"] for r in node_closed)
        n_wins = sum(1 for r in node_closed if r["net_pnl"] > 0)
        n_wr = (n_wins / len(node_closed) * 100.0) if node_closed else 0.0
        node_summaries.append(
            f"  ? <code>{nid}</code>: {len(node_closed)} tr | WR {n_wr:.0f}% | PnL <b>${n_pnl:+,.2f}</b> | Eq <code>${eq:,.2f}</code>"
        )

        mt5.shutdown()
        gc.collect()

    nodes_text = "\n".join(node_summaries)
    metrics = compute_metrics(all_closed)

    if not metrics:
        report_msg = (
            f"?? <b>[QUANTNEXUS 4-NODE ALPHA REPORT]</b> Rolling 7-Day\n"
            f"? Range: <code>{from_date.strftime('%Y-%m-%d')} -> {now_utc.strftime('%Y-%m-%d')}</code>\n"
            f"? Status: <i>0 closed round-turn deals in rolling 7-day window</i>\n\n"
            f"<b>Terminal Nodes (T1?T4):</b>\n{nodes_text}\n\n"
            f"? Cluster Balance: <code>${total_balance:,.2f}</code> | Equity: <code>${total_equity:,.2f}</code>"
        )
    else:
        pnl_badge = "??" if metrics["net_profit"] >= 0 else "??"
        sym_lines = []
        for sym, sdata in sorted(metrics["symbols"].items(), key=lambda kv: kv[1]["pnl"], reverse=True):
            wr = (sdata["wins"] / sdata["trades"] * 100.0) if sdata["trades"] > 0 else 0.0
            sym_lines.append(f"  ? <code>{sym:<8}</code>: {sdata['trades']} trades | WR: {wr:.0f}% | PnL: ${sdata['pnl']:+,.2f}")
        symbols_text = "\n".join(sym_lines)

        report_msg = (
            f"?? <b>[QUANTNEXUS 4-NODE ALPHA REPORT]</b> Rolling 7-Day Performance\n"
            f"? Range: <code>{from_date.strftime('%Y-%m-%d')} -> {now_utc.strftime('%Y-%m-%d')}</code>\n\n"
            f"<b>Cluster Risk & Profit Metrics (T1?T4):</b>\n"
            f"? Net Realized PnL: <b>${metrics['net_profit']:+,.2f}</b> {pnl_badge}\n"
            f"? Total Trades: <code>{metrics['total_trades']}</code> (Win Rate: <b>{metrics['win_rate']:.1f}%</b>)\n"
            f"? Profit Factor: <b>{metrics['profit_factor']:.2f}</b>\n"
            f"? Sharpe Ratio: <code>{metrics['sharpe']:.2f}</code> | Sortino: <code>{metrics['sortino']:.2f}</code>\n"
            f"? Max Trade Drawdown: <code>${metrics['max_dd']:,.2f}</code>\n"
            f"? Avg Win: <code>${metrics['avg_win']:,.2f}</code> | Avg Loss: <code>${metrics['avg_loss']:,.2f}</code>\n\n"
            f"<b>Per-Terminal Attribution (T1?T4):</b>\n{nodes_text}\n\n"
            f"<b>Symbol Attribution:</b>\n{symbols_text}\n\n"
            f"? Cluster Balance: <code>${total_balance:,.2f}</code> | Equity: <code>${total_equity:,.2f}</code>"
        )

    print("\n" + report_msg + "\n")
    if broadcast:
        logger.info("Sending 4-node weekly performance digest to Telegram...")
        send_alert("quant_alert_bot", report_msg)
        send_godmode_alert(report_msg)
        logger.info("Weekly Alpha Report generated and dispatched successfully.")


if __name__ == "__main__":
    no_bcast = ("--dry-run" in sys.argv)
    generate_weekly_report(broadcast=not no_bcast)
