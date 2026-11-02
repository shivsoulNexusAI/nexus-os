"""
SHIVSOUL SOVEREIGN NEXUS // IMMUTABLE PERFORMANCE LEDGER (nexus_ledger.py)
Synchronizes closed MT5 deals into an SQLite datastore and computes institutional
risk-adjusted performance metrics (Sharpe, Sortino, Profit Factor, Max Drawdown).
"""
import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nexus_ledger.db")
METRICS_JSON_PATH = os.path.join(BASE_DIR, "performance_metrics.json")

class NexusLedger:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes SQLite tables for immutable trade recording."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS closed_deals (
                    deal_ticket INTEGER PRIMARY KEY,
                    order_ticket INTEGER,
                    symbol TEXT,
                    deal_type TEXT,
                    volume REAL,
                    price REAL,
                    profit REAL,
                    commission REAL,
                    swap REAL,
                    net_pnl REAL,
                    magic INTEGER,
                    close_time TIMESTAMP,
                    comment TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_snapshots (
                    timestamp TIMESTAMP PRIMARY KEY,
                    net_pnl REAL,
                    win_rate REAL,
                    profit_factor REAL,
                    sharpe_ratio REAL,
                    sortino_ratio REAL,
                    max_drawdown_pct REAL,
                    trade_count INTEGER
                )
            """)
            conn.commit()

    def sync_mt5_history(self, lookback_days: int = 90) -> int:
        """Polls MT5 historical deals and records new closed deals immutably."""
        if not HAS_MT5 or not mt5.initialize():
            return 0

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=lookback_days)

        deals = mt5.history_deals_get(start, now)
        if not deals:
            return 0

        new_records = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for d in deals:
                # MT5 deal entry: 0 = IN (open), 1 = OUT (close), 2 = INOUT (reverse)
                if d.entry not in (1, 2) or d.symbol == "":
                    continue

                net_pnl = d.profit + d.commission + d.swap
                deal_type = "SELL" if d.type == 1 else "BUY"
                deal_time = datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat()

                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO closed_deals (
                            deal_ticket, order_ticket, symbol, deal_type, volume,
                            price, profit, commission, swap, net_pnl, magic, close_time, comment
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        d.ticket, d.order, d.symbol, deal_type, d.volume,
                        d.price, d.profit, d.commission, d.swap, net_pnl, d.magic, deal_time, d.comment
                    ))
                    if cursor.rowcount > 0:
                        new_records += 1
                except sqlite3.Error:
                    pass

            conn.commit()
        return new_records

    def calculate_analytics(self, risk_free_rate: float = 0.04) -> Dict[str, Any]:
        """Calculates institutional performance metrics (Sharpe, Sortino, Drawdown)."""
        with self._get_connection() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM closed_deals ORDER BY close_time ASC",
                conn,
                parse_dates=["close_time"]
            )

        if df.empty:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "net_profit": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_usd": 0.0,
                "max_drawdown_pct": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0
            }

        pnls = df["net_pnl"].to_numpy()
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        total_trades = len(pnls)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        gross_profit = float(np.sum(wins)) if win_count > 0 else 0.0
        gross_loss = float(abs(np.sum(losses))) if loss_count > 0 else 0.0
        net_profit = float(np.sum(pnls))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # Equity Curve and Peak Drawdown
        equity_curve = np.cumsum(pnls)
        peak = np.maximum.accumulate(equity_curve)
        drawdowns = peak - equity_curve
        max_dd_usd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        starting_balance = 10000.0
        if HAS_MT5 and mt5.initialize():
            acc = mt5.account_info()
            if acc and acc.balance > 0:
                starting_balance = max(acc.balance - net_profit, 1000.0)

        rel_equity = starting_balance + equity_curve
        rel_peak = np.maximum.accumulate(rel_equity)
        pct_drawdowns = (rel_peak - rel_equity) / rel_peak
        max_dd_pct = float(np.max(pct_drawdowns)) * 100.0 if len(pct_drawdowns) > 0 else 0.0

        # Sharpe & Sortino Calculations (Annualized to 252 trading sessions)
        rf_per_trade = risk_free_rate / 252.0
        mean_pnl = float(np.mean(pnls))
        std_pnl = float(np.std(pnls)) if len(pnls) > 1 else 0.0

        downside_diffs = np.minimum(pnls - rf_per_trade, 0.0)
        downside_std = float(np.sqrt(np.mean(downside_diffs ** 2))) if len(downside_diffs) > 0 else 0.0

        annualizer = np.sqrt(252)
        sharpe = ((mean_pnl - rf_per_trade) / std_pnl * annualizer) if std_pnl > 0 else 0.0
        sortino = ((mean_pnl - rf_per_trade) / downside_std * annualizer) if downside_std > 0 else 0.0

        summary = {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "net_profit": round(net_profit, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "avg_win": round(float(np.mean(wins)), 2) if len(wins) > 0 else 0.0,
            "avg_loss": round(float(np.mean(losses)), 2) if len(losses) > 0 else 0.0,
            "sharpe_ratio": round(float(np.clip(sharpe, -10.0, 15.0)), 2),
            "sortino_ratio": round(float(np.clip(sortino, -10.0, 25.0)), 2),
            "max_drawdown_usd": round(max_dd_usd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

        # Cache metrics to disk for Streamlit dashboard consumption
        import json
        with open(METRICS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        return summary

nexus_ledger = NexusLedger()

if __name__ == "__main__":
    print("[*] Synchronizing MT5 closed deals into Nexus Ledger...")
    synced = nexus_ledger.sync_mt5_history(lookback_days=90)
    print(f"🟢 Synchronized {synced} new closed deals.")
    metrics = nexus_ledger.calculate_analytics()
    print("\n--- INSTITUTIONAL PERFORMANCE LEDGER ---")
    for k, v in metrics.items():
        print(f"• {k:<18}: {v}")


# Backward-compatibility alias for Sovereign Sentry
SovereignLedger = NexusLedger
