# -*- coding: utf-8 -*-
"""
QuantNexus Session-Close P&L Digest Daemon
Calculates Gross Profit, Fees, Swaps, Net P&L, Win Rate, and Profit Factor
across T1 (#278017866), T2 (#278041169), and T3 (#278041671).
Fires at London Close (16:00 UTC) and NY Close (21:00 UTC), or on-demand (--now).
"""
import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import MetaTrader5 as mt5

CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\session_pnl_digest.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("SessionDigest")

FLEET = [
    {"tag": "T1 Institutional", "login": 278017866, "path": r"C:\MT5_Quant_278017866\terminal64.exe"},
    {"tag": "T2 4 Majors Grid", "login": 278041169, "path": r"C:\MT5_Pending_278041169\terminal64.exe"},
    {"tag": "T3 Gold HFT",      "login": 278041671, "path": r"C:\MT5_HFT_278041671\terminal64.exe"}
]

def load_telegram_cfg():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("bot_token"), data.get("authorized_chat_id")
    except Exception:
        return None, None

def send_telegram_digest(card_text: str):
    token, chat_id = load_telegram_cfg()
    if not token or not chat_id:
        log.error("Missing Telegram configuration.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": card_text,
        "parse_mode": "HTML"
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                log.info("Session digest successfully posted to Telegram.")
            else:
                log.error("Telegram error: %s", resp.text)
    except Exception as e:
        log.error("Dispatch failure: %s", e)

def audit_account_session(term_info: dict, start_utc: datetime, end_utc: datetime) -> dict:
    tag = term_info["tag"]
    login = term_info["login"]
    path = term_info["path"]

    if not mt5.initialize(path=path):
        return {"tag": tag, "login": login, "error": "Terminal IPC failure"}

    acc = mt5.account_info()
    if not acc or acc.login != login:
        mt5.shutdown()
        return {"tag": tag, "login": login, "error": f"Account mismatch (#{getattr(acc, 'login', None)})"}

    deals = mt5.history_deals_get(start_utc, end_utc)
    mt5.shutdown()

    if deals is None:
        deals = []

    # Filter out pure deposit/withdrawal balance operations
    trade_deals = [d for d in deals if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT) and d.profit != 0]

    gross_profit = 0.0
    gross_loss = 0.0
    total_commission = sum(d.commission for d in deals)
    total_swap = sum(d.swap for d in deals)
    total_profit = sum(d.profit for d in trade_deals)
    
    wins = 0
    losses = 0

    for d in trade_deals:
        if d.profit > 0:
            gross_profit += d.profit
            wins += 1
        elif d.profit < 0:
            gross_loss += abs(d.profit)
            losses += 1

    net_pnl = total_profit + total_commission + total_swap
    total_closed = len(trade_deals)
    win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)

    return {
        "tag": tag,
        "login": login,
        "balance": acc.balance,
        "equity": acc.equity,
        "total_closed": total_closed,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "commission": total_commission,
        "swap": total_swap,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor
    }

def generate_session_digest(session_name: str = "MANUAL AUDIT", hours_back: int = 12):
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(hours=hours_back)

    log.info("Generating Session Digest: %s (Period: %s -> %s)", session_name, start_utc, now_utc)

    fleet_results = []
    total_fleet_net = 0.0
    total_fleet_comm = 0.0
    total_fleet_swaps = 0.0
    total_fleet_trades = 0

    for term in FLEET:
        res = audit_account_session(term, start_utc, now_utc)
        fleet_results.append(res)
        if "error" not in res:
            total_fleet_net += res["net_pnl"]
            total_fleet_comm += res["commission"]
            total_fleet_swaps += res["swap"]
            total_fleet_trades += res["total_closed"]

    # Build Telegram Card
    net_icon = "🟢" if total_fleet_net >= 0 else "🔴"
    card = [
        f"📋 <b>QUANTNEXUS // SESSION P&amp;L DIGEST</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Session:</b> <code>{session_name}</code>",
        f"<b>Timestamp:</b> <code>{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>",
        f"<b>Window:</b> Trailing {hours_back}h",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>FLEET AGGREGATE RETURN:</b> {net_icon} <code>${total_fleet_net:+,.2f}</code>",
        f"<b>Total Closed Trades:</b> <code>{total_fleet_trades}</code>",
        f"<b>Commissions:</b> <code>${total_fleet_comm:.2f}</code> | <b>Swaps:</b> <code>${total_fleet_swaps:.2f}</code>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 <b>PER-TERMINAL BREAKDOWN:</b>"
    ]

    for r in fleet_results:
        if "error" in r:
            card.append(f"• <b>{r['tag']}</b> (<code>#{r['login']}</code>): ⚠️ {r['error']}")
        else:
            pnl_tag = "🟢" if r["net_pnl"] >= 0 else "🔴"
            card.append(
                f"• <b>{r['tag']}</b> [<code>#{r['login']}</code>]\n"
                f"   Net P&amp;L: {pnl_tag} <code>${r['net_pnl']:+,.2f}</code> | WR: <code>{r['win_rate']:.1f}%</code> ({r['wins']}W/{r['losses']}L)\n"
                f"   PF: <code>{r['profit_factor']:.2f}</code> | Equity: <code>${r['equity']:,.2f}</code>"
            )

    card.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    card.append(f"<i>Autonomous institutional telemetry by QuantNexus.</i>")

    full_text = "\n".join(card)
    send_telegram_digest(full_text)

def daemon_loop():
    log.info("Session-Close P&L Digest Daemon engaged.")
    log.info("Target Schedule: 16:00:00 UTC (London Close) and 21:00:00 UTC (NY Close).")
    
    last_dispatched = None

    while True:
        now_utc = datetime.now(timezone.utc)
        current_minute = (now_utc.hour, now_utc.minute)

        # London Session Close (16:00 UTC)
        if current_minute == (16, 0) and last_dispatched != "LDN":
            generate_session_digest(session_name="LONDON SESSION CLOSE", hours_back=9)
            last_dispatched = "LDN"
            time.sleep(60)

        # New York Session Close (21:00 UTC)
        elif current_minute == (21, 0) and last_dispatched != "NY":
            generate_session_digest(session_name="NEW YORK SESSION CLOSE", hours_back=9)
            last_dispatched = "NY"
            time.sleep(60)

        if now_utc.minute not in (0, 1):
            last_dispatched = None

        time.sleep(20)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        generate_session_digest("ON-DEMAND MANUAL PROBE", hours_back=24)
    else:
        daemon_loop()