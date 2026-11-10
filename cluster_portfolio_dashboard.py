"""
QUANTNEXUS UNIFIED CROSS-TERMINAL PORTFOLIO DASHBOARD (v1.0 Production)
Inspects and aggregates account equity, balance, floating PnL, margin utilization,
and active symbol exposure across all three MT5 terminal nodes on the 1GB VPS.
"""
import os
import gc
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_logging_guard import get_rotating_logger
from nexus_state_guard import read_risk_state
from nexus_telegram import send_alert

logger = get_rotating_logger("ClusterDashboard", "cluster_dashboard.log")

TERMINAL_CONFIG = [
    {
        "id": "TERM_QUANT_278017866",
        "path": "C:/MT5_Quant_278017866/terminal64.exe"
    },
    {
        "id": "TERM_HFT_278041671",
        "path": "C:/MT5_HFT_278041671/terminal64.exe"
    },
    {
        "id": "TERM_PENDING_278041169",
        "path": "C:/MT5_Pending_278041169/terminal64.exe"
    }
]

class ClusterPortfolioDashboard:
    def __init__(self, terminals: List[Dict[str, str]] = TERMINAL_CONFIG):
        self.terminals = terminals

    def query_terminal_metrics(self, node: Dict[str, str]) -> Optional[Dict[str, Any]]:
        path = node["path"]
        term_id = node["id"]

        if not os.path.exists(path):
            return {"id": term_id, "status": "OFFLINE", "error": "Path Not Found"}

        if not mt5.initialize(path=path):
            err = mt5.last_error()
            return {"id": term_id, "status": "OFFLINE", "error": f"Init Error: {err}"}

        acc = mt5.account_info()
        positions = mt5.positions_get()

        if acc is None:
            mt5.shutdown()
            gc.collect()
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
                    "magic": p.magic
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
            "positions": pos_list
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
            "daily_loss_pct": risk_state.get("daily_loss_pct", 0.0)
        }

    def render_console_dashboard(self, summary: Dict[str, Any]):
        print("\n" + "=" * 80)
        print("          QUANTNEXUS UNIFIED CROSS-TERMINAL PORTFOLIO DASHBOARD")
        print("=" * 80)
        print(f"Timestamp: {summary['timestamp_utc']} | Breaker Tripped: {summary['circuit_breaker_tripped']} | Daily Loss: {summary['daily_loss_pct']:.2f}%")
        print("-" * 80)
        print(f"{'Node ID':<24} | {'Login':<11} | {'Status':<7} | {'Balance':>10} | {'Equity':>10} | {'Open PnL':>9} | {'Pos':>3}")
        print("-" * 80)

        for n in summary["nodes"]:
            if n.get("status") == "ONLINE":
                print(f"{n['id']:<24} | #{n['login']:<10} | ONLINE  | ${n['balance']:>9.2f} | ${n['equity']:>9.2f} | ${n['profit']:>8.2f} | {n['positions_count']:>3}")
            else:
                print(f"{n['id']:<24} | {'N/A':<10} | OFFLINE | {'--':>10} | {'--':>10} | {'--':>9} |   0")

        print("-" * 80)
        print(f"CLUSTER TOTALS: Balance: ${summary['total_balance']:,.2f} | Equity: ${summary['total_equity']:,.2f} | Floating PnL: ${summary['total_profit']:,.2f}")
        print(f"Margin Used: ${summary['total_margin']:,.2f} | Margin Level: {summary['cluster_margin_level']:.1f}% | Total Positions: {summary['total_positions']}")
        
        if summary["symbol_net_exposure"]:
            print("\nNet Cluster Symbol Exposure:")
            for sym, exp in summary["symbol_net_exposure"].items():
                bias = "LONG" if exp > 0 else ("SHORT" if exp < 0 else "FLAT")
                print(f"  • {sym:<10}: {abs(exp):>5.2f} lots [{bias}]")
        else:
            print("\nNet Cluster Symbol Exposure: None (Flat across all 3 nodes)")
        print("=" * 80 + "\n")

    def broadcast_telegram_snapshot(self, summary: Dict[str, Any]):
        node_lines = []
        for n in summary["nodes"]:
            if n.get("status") == "ONLINE":
                node_lines.append(f"  • <code>{n['id']}</code>: <b>${n['equity']:,.2f}</b> (${n['profit']:+,.2f})")
            else:
                node_lines.append(f"  • <code>{n['id']}</code>: <b>OFFLINE</b>")

        nodes_str = "\n".join(node_lines)
        exp_lines = [f"  • <code>{sym}</code>: {exp:+.2f} lots" for sym, exp in summary["symbol_net_exposure"].items()]
        exp_str = "\n".join(exp_lines) if exp_lines else "  • <i>Flat across all nodes</i>"

        msg = (
            f"📊 <b>QUANTNEXUS CLUSTER PORTFOLIO SNAPSHOT</b>\n"
            f"• Aggregate Equity: <b>${summary['total_equity']:,.2f}</b>\n"
            f"• Floating PnL: <b>${summary['total_profit']:+,.2f}</b>\n"
            f"• Margin Level: <b>{summary['cluster_margin_level']:.1f}%</b>\n\n"
            f"<b>Terminal Nodes:</b>\n{nodes_str}\n\n"
            f"<b>Net Exposure:</b>\n{exp_str}\n"
            f"• Circuit Breaker: <code>{'TRIPPED' if summary['circuit_breaker_tripped'] else 'ACTIVE'}</code>"
        )
        send_alert("quant_alert_bot", msg)

if __name__ == "__main__":
    dashboard = ClusterPortfolioDashboard()
    summary = dashboard.aggregate_cluster_portfolio()
    dashboard.render_console_dashboard(summary)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--broadcast":
        dashboard.broadcast_telegram_snapshot(summary)
        print("[+] Telegram cluster snapshot broadcast complete.")
