"""
QUANTNEXUS UNIFIED CROSS-TERMINAL PORTFOLIO DASHBOARD (v1.1 Production - 4-Terminal Cluster)
Inspects and aggregates account equity, balance, floating PnL, margin utilization,
and active symbol exposure across all four MT5 terminal nodes (T1-T4) on AdmVps.
"""
import os
import gc
import sys
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_logging_guard import get_rotating_logger
from nexus_state_guard import read_risk_state
from nexus_telegram import send_alert

logger = get_rotating_logger("ClusterDashboard", "cluster_dashboard.log")

LEDGER_DB = r"C:\Quant-Nexus-Eng\nexus_ledger.db"
GODMODE_TOKEN = "8500432698:AAFLDz1nN_JeSMo2HBNx2gujV7tSlMfQGGg"
GODMODE_CHAT_ID = "5279761713"

TERMINAL_CONFIG = [
    {
        "id": "T1_BTC_278062038",
        "sleeve": "T1",
        "path": "C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe",
        "portable": False,
    },
    {
        "id": "T2_FX_278062039",
        "sleeve": "T2",
        "path": "C:/MT5_Pending_278041169/terminal64.exe",
        "portable": False,
    },
    {
        "id": "T3_XAU_278062042",
        "sleeve": "T3",
        "path": "C:/MT5_HFT_278041671/terminal64.exe",
        "portable": False,
    },
    {
        "id": "T4_APEX_278071462",
        "sleeve": "T4",
        "path": "C:/MT5_Sovereign_T4/terminal64.exe",
        "portable": True,
    },
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


def query_ledger_heartbeat_fallback(sleeve: str, term_id: str) -> Optional[Dict[str, Any]]:
    """Fallback to nexus_ledger.db worker_heartbeats if an active worker holds the MT5 IPC pipe."""
    if not os.path.exists(LEDGER_DB):
        return None
    try:
        conn = sqlite3.connect(LEDGER_DB, timeout=5.0)
        row = conn.execute(
            "SELECT login, equity, open_count, last_tick_utc, status FROM worker_heartbeats WHERE sleeve = ?",
            (sleeve,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        login, equity, open_cnt, last_tick, status = row
        eq = float(equity or 0.0)
        return {
            "id": term_id,
            "status": "ONLINE",
            "login": int(login),
            "server": "Exness-MT5Trial5",
            "currency": "USD",
            "balance": eq,
            "equity": eq,
            "profit": 0.0,
            "margin": 0.0,
            "margin_free": eq,
            "margin_level": 0.0,
            "positions_count": int(open_cnt or 0),
            "positions": [],
            "source": f"LEDGER_HB({status})",
        }
    except Exception:
        return None


class ClusterPortfolioDashboard:
    def __init__(self, terminals: List[Dict[str, Any]] = TERMINAL_CONFIG):
        self.terminals = terminals

    def query_terminal_metrics(self, node: Dict[str, Any]) -> Dict[str, Any]:
        path = node["path"]
        term_id = node["id"]
        sleeve = node.get("sleeve", "")
        portable = bool(node.get("portable", False))

        if not os.path.exists(path):
            return {"id": term_id, "status": "OFFLINE", "error": "Path Not Found"}

        init_ok = mt5.initialize(path=path, portable=True) if portable else mt5.initialize(path=path)
        if not init_ok:
            err = mt5.last_error()
            fb = query_ledger_heartbeat_fallback(sleeve, term_id)
            if fb:
                return fb
            return {"id": term_id, "status": "OFFLINE", "error": f"Init Error: {err}"}

        acc = mt5.account_info()
        positions = mt5.positions_get()

        if acc is None:
            mt5.shutdown()
            gc.collect()
            fb = query_ledger_heartbeat_fallback(sleeve, term_id)
            if fb:
                return fb
            return {"id": term_id, "status": "ERROR", "error": "Failed account_info"}

        pos_list = []
        if positions:
            for p in positions:
                pos_list.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": p.volume,
                    "open_price": p.price_open,
                    "current_price": p.price_current,
                    "profit": p.profit,
                    "magic": p.magic,
                })

        data = {
            "id": term_id,
            "status": "ONLINE",
            "login": acc.login,
            "server": acc.server,
            "currency": acc.currency,
            "balance": float(acc.balance),
            "equity": float(acc.equity),
            "profit": float(acc.profit),
            "margin": float(acc.margin),
            "margin_free": float(acc.margin_free),
            "margin_level": float(acc.margin_level) if acc.margin > 0 else 0.0,
            "positions_count": len(pos_list),
            "positions": pos_list,
        }

        mt5.shutdown()
        gc.collect()
        return data

    def aggregate_cluster_portfolio(self) -> Dict[str, Any]:
        node_results = []
        total_balance = 0.0
        total_equity = 0.0
        total_profit = 0.0
        total_margin = 0.0
        total_positions = 0
        symbol_net_exposure: Dict[str, float] = {}

        for node in self.terminals:
            res = self.query_terminal_metrics(node)
            node_results.append(res)
            if res.get("status") == "ONLINE":
                total_balance += res["balance"]
                total_equity += res["equity"]
                total_profit += res["profit"]
                total_margin += res["margin"]
                total_positions += res["positions_count"]

                for pos in res.get("positions", []):
                    sym = pos["symbol"]
                    signed_vol = pos["volume"] if pos["type"] == "BUY" else -pos["volume"]
                    symbol_net_exposure[sym] = round(symbol_net_exposure.get(sym, 0.0) + signed_vol, 2)

        risk_state = read_risk_state()
        cluster_margin_level = (total_equity / total_margin * 100.0) if total_margin > 0 else 0.0

        return {
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "nodes": node_results,
            "total_balance": round(total_balance, 2),
            "total_equity": round(total_equity, 2),
            "total_profit": round(total_profit, 2),
            "total_margin": round(total_margin, 2),
            "cluster_margin_level": round(cluster_margin_level, 2),
            "total_positions": total_positions,
            "symbol_net_exposure": symbol_net_exposure,
            "circuit_breaker_tripped": risk_state.get("circuit_breaker_tripped", False),
            "daily_loss_pct": risk_state.get("daily_loss_pct", 0.0),
        }

    def render_console_dashboard(self, summary: Dict[str, Any]):
        print("\n" + "=" * 84)
        print("        QUANTNEXUS UNIFIED 4-TERMINAL CLUSTER PORTFOLIO DASHBOARD (T1 - T4)")
        print("=" * 84)
        print(f"Timestamp: {summary['timestamp_utc']} | Breaker Tripped: {summary['circuit_breaker_tripped']} | Daily Loss: {summary['daily_loss_pct']:.2f}%")
        print("-" * 84)
        print(f"{'Node ID':<26} | {'Login':<11} | {'Status':<7} | {'Balance':>10} | {'Equity':>10} | {'Open PnL':>9} | {'Pos':>3}")
        print("-" * 84)

        for n in summary["nodes"]:
            if n.get("status") == "ONLINE":
                print(f"{n['id']:<26} | #{n['login']:<10} | ONLINE  | ${n['balance']:>9.2f} | ${n['equity']:>9.2f} | ${n['profit']:>8.2f} | {n['positions_count']:>3}")
            else:
                print(f"{n['id']:<26} | {'N/A':<10} | OFFLINE | {'--':>10} | {'--':>10} | {'--':>9} |   0")

        print("-" * 84)
        print(f"CLUSTER TOTALS: Balance: ${summary['total_balance']:,.2f} | Equity: ${summary['total_equity']:,.2f} | Floating PnL: ${summary['total_profit']:,.2f}")
        print(f"Margin Used: ${summary['total_margin']:,.2f} | Margin Level: {summary['cluster_margin_level']:.1f}% | Total Positions: {summary['total_positions']}")

        if summary["symbol_net_exposure"]:
            print("\nNet Cluster Symbol Exposure:")
            for sym, exp in summary["symbol_net_exposure"].items():
                bias = "LONG" if exp > 0 else ("SHORT" if exp < 0 else "FLAT")
                print(f"  * {sym:<10}: {abs(exp):>5.2f} lots [{bias}]")
        else:
            print("\nNet Cluster Symbol Exposure: None (Flat across all 4 nodes)")
        print("=" * 84 + "\n")

    def broadcast_telegram_snapshot(self, summary: Dict[str, Any]):
        node_lines = []
        for n in summary["nodes"]:
            if n.get("status") == "ONLINE":
                node_lines.append(f"  ? <code>{n['id']}</code>: <b>${n['equity']:,.2f}</b> (${n['profit']:+,.2f})")
            else:
                node_lines.append(f"  ? <code>{n['id']}</code>: <b>OFFLINE</b>")

        nodes_str = "\n".join(node_lines)
        exp_lines = [f"  ? <code>{sym}</code>: {exp:+.2f} lots" for sym, exp in summary["symbol_net_exposure"].items()]
        exp_str = "\n".join(exp_lines) if exp_lines else "  ? <i>Flat across all nodes</i>"

        msg = (
            f"?? <b>QUANTNEXUS 4-NODE CLUSTER PORTFOLIO SNAPSHOT</b>\n"
            f"? Aggregate Equity: <b>${summary['total_equity']:,.2f}</b>\n"
            f"? Floating PnL: <b>${summary['total_profit']:+,.2f}</b>\n"
            f"? Margin Level: <b>{summary['cluster_margin_level']:.1f}%</b>\n\n"
            f"<b>Terminal Nodes (T1?T4):</b>\n{nodes_str}\n\n"
            f"<b>Net Exposure:</b>\n{exp_str}\n"
            f"? Circuit Breaker: <code>{'TRIPPED' if summary['circuit_breaker_tripped'] else 'ACTIVE'}</code>"
        )
        send_alert("quant_alert_bot", msg)
        send_godmode_alert(msg)


if __name__ == "__main__":
    dashboard = ClusterPortfolioDashboard()
    summary = dashboard.aggregate_cluster_portfolio()
    dashboard.render_console_dashboard(summary)

    if len(sys.argv) > 1 and sys.argv[1] == "--broadcast":
        dashboard.broadcast_telegram_snapshot(summary)
        print("[+] Telegram 4-node cluster snapshot broadcast complete.")
