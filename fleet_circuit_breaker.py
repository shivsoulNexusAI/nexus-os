"""
QuantNexus Fleet-Wide Circuit Breaker Guardian
Monitors aggregate and per-terminal floating drawdown across T1, T2, and T3.
"""
import sys
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import httpx
import MetaTrader5 as mt5

sys.stdout.reconfigure(line_buffering=True)

CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\circuit_breaker.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("CircuitBreaker")

FLEET = [
    {"name": "T1 Silver Bullet", "path": r"C:\MT5_Quant_278017866\terminal64.exe", "login": 278017866, "max_dd_pct": 0.04},
    {"name": "T2 4 Majors Grid", "path": r"C:\MT5_Pending_278041169\terminal64.exe", "login": 278041169, "max_dd_pct": 0.05},
    {"name": "T3 Gold HFT", "path": r"C:\MT5_HFT_278041671\terminal64.exe", "login": 278041671, "max_dd_pct": 0.04}
]
FLEET_MAX_AGGREGATE_DD_PCT = 0.06 # 6% maximum aggregate drawdown
POLL_INTERVAL_SEC = 5

def load_telegram_cfg():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("bot_token"), data.get("authorized_chat_id")
    except Exception:
        return None, None

def send_emergency_alert(msg: str):
    token, chat_id = load_telegram_cfg()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=8.0) as client:
            client.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        log.warning("Alert send failed: %s", e)

def emergency_flatten_terminal(term_path: str, login_id: int, reason: str):
    """Liquidates all market positions and cancels all pending orders on a terminal."""
    if not mt5.initialize(path=term_path):
        log.error("Emergency flatten: could not initialize %s", term_path)
        return

    acc = mt5.account_info()
    if not acc or acc.login != login_id:
        mt5.shutdown()
        return

    # 1. Close all open market positions
    positions = mt5.positions_get() or []
    for p in positions:
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        sym_info = mt5.symbol_info(p.symbol)
        price = sym_info.bid if close_type == mt5.ORDER_TYPE_SELL else sym_info.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "price": price,
            "deviation": 20,
            "magic": p.magic,
            "comment": f"CIRCUIT_BREAKER_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        log.info("Close order ticket #%s result: %s", p.ticket, getattr(res, 'retcode', 'failed'))

    # 2. Cancel all pending orders
    orders = mt5.orders_get() or []
    for o in orders:
        req = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": o.ticket
        }
        res = mt5.order_send(req)
        log.info("Cancel pending ticket #%s result: %s", o.ticket, getattr(res, 'retcode', 'failed'))

    mt5.shutdown()

    alert_text = (
        f"🚨 <b>[CIRCUIT BREAKER ENGAGED: FLATTENED]</b>\n\n"
        f"<b>Terminal:</b> <code>#{login_id}</code>\n"
        f"<b>Trigger Cause:</b> <code>{reason}</code>\n"
        f"<b>Action:</b> Liquidated {len(positions)} positions, Purged {len(orders)} pendings.\n"
        f"<i>Fleet protection active. Trading paused on this wing.</i>"
    )
    send_emergency_alert(alert_text)

def inspect_fleet():
    total_balance = 0.0
    total_equity = 0.0

    for term in FLEET:
        if not mt5.initialize(path=term["path"]):
            continue
        acc = mt5.account_info()
        if not acc or acc.login != term["login"]:
            mt5.shutdown()
            continue

        bal = acc.balance
        eq = acc.equity
        floating = eq - bal
        dd_pct = (bal - eq) / bal if bal > 0 else 0.0

        total_balance += bal
        total_equity += eq
        mt5.shutdown()

        # Check individual terminal breaker threshold
        if dd_pct >= term["max_dd_pct"]:
            log.critical("Breaker tripped on %s! DD: %.2f%% >= %.2f%%", term["name"], dd_pct * 100, term["max_dd_pct"] * 100)
            emergency_flatten_terminal(
                term["path"],
                term["login"],
                f"Terminal Drawdown reached {dd_pct*100:.2f}% (Limit: {term['max_dd_pct']*100:.1f}%)"
            )

    # Check aggregate cross-fleet breaker threshold
    if total_balance > 0:
        agg_dd_pct = (total_balance - total_equity) / total_balance
        if agg_dd_pct >= FLEET_MAX_AGGREGATE_DD_PCT:
            log.critical("GLOBAL FLEET BREAKER TRIPPED! Combined DD: %.2f%% >= %.2f%%", agg_dd_pct * 100, FLEET_MAX_AGGREGATE_DD_PCT * 100)
            for term in FLEET:
                emergency_flatten_terminal(
                    term["path"],
                    term["login"],
                    f"Global Fleet Drawdown reached {agg_dd_pct*100:.2f}% (Limit: {FLEET_MAX_AGGREGATE_DD_PCT*100:.1f}%)"
                )

if __name__ == "__main__":
    log.info("Starting QuantNexus Fleet-Wide Circuit Breaker Sentinel...")
    while True:
        try:
            inspect_fleet()
        except Exception as e:
            log.error("Audit cycle exception: %s", e)
        time.sleep(POLL_INTERVAL_SEC)
