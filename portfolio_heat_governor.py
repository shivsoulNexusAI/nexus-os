# -*- coding: utf-8 -*-
"""
QUANT-NEXUS v11.3 CROSS-SLEEVE PORTFOLIO USD CORRELATION & NET HEAT GOVERNOR
Synchronizes live open risk across T1 (#278062038), T2 (#278062039), and T3 (#278062042)
via SQLite WAL mode in nexus_ledger.db.
- Exempts risk-free positions locked at/beyond breakeven (SL >= entry for BUY, SL <= entry for SELL).
- Caps net directional USD factor beta at 1.5 units and total open fleet risk at $9.50.
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_ledger.db")

MAX_NET_USD_BETA = 1.50
MAX_FLEET_OPEN_RISK_USD = 9.50

DEFAULT_SLEEVE_RISK_USD = {
    "T1": 4.50,
    "T2": 3.00,
    "T3": 4.50,
}

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS active_fleet_exposure (
            sleeve TEXT NOT NULL,
            ticket INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            risk_usd REAL NOT NULL,
            usd_beta REAL NOT NULL,
            is_risk_free INTEGER NOT NULL DEFAULT 0,
            updated_utc TEXT NOT NULL,
            PRIMARY KEY (sleeve, ticket)
        )
    """)
    conn.commit()
    return conn

def get_usd_factor_beta(symbol: str, direction: str) -> float:
    """
    Returns signed USD directional factor exposure for a trade:
    - BUY BTCUSD / GBPUSD / XAUUSD = -1.0 (Short USD) | SELL = +1.0 (Long USD)
    - BUY US30 = -0.5 (Soft USD / Risk-On) | SELL = +0.5 (Firm USD / Risk-Off)
    """
    sym = symbol.upper()
    is_buy = (direction.upper() == "BUY")
    if any(k in sym for k in ("XAU", "BTC", "GBP", "EUR", "AUD", "NZD")):
        return -1.0 if is_buy else 1.0
    if "USDJPY" in sym or "USDCAD" in sym or "USDCHF" in sym:
        return 1.0 if is_buy else -1.0
    if "US30" in sym or "USTEC" in sym or "US500" in sym:
        return -0.5 if is_buy else 0.5
    return 0.0

def _estimate_position_open_risk(sleeve_key: str, pos, sym_info) -> tuple[float, bool]:
    """
    Computes remaining dollar risk to stop-loss.
    Returns (remaining_risk_usd, is_risk_free_be).
    """
    entry = float(pos.price_open)
    sl = float(pos.sl)
    vol = float(pos.volume)
    is_buy = (int(pos.type) == 0)

    if sl > 0.0:
        if (is_buy and sl >= entry) or (not is_buy and sl <= entry):
            return 0.0, True
        if sym_info is not None and sym_info.trade_tick_size > 0 and sym_info.trade_tick_value > 0:
            stop_dist = abs(entry - sl)
            usd_per_unit = float(sym_info.trade_tick_value) / float(sym_info.trade_tick_size)
            rem_usd = round(stop_dist * usd_per_unit * vol, 2)
            return max(0.0, rem_usd), False

    return DEFAULT_SLEEVE_RISK_USD.get(sleeve_key, 4.50), False

def sync_sleeve_exposure(sleeve_key: str, positions: list, sym_info_map: dict | None = None, now_utc: datetime | None = None) -> None:
    """
    Replaces `sleeve_key` rows in active_fleet_exposure with current live MT5 positions.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    ts_str = now_utc.isoformat()
    sym_info_map = sym_info_map or {}

    conn = _connect()
    try:
        conn.execute("DELETE FROM active_fleet_exposure WHERE sleeve = ?", (sleeve_key,))
        for p in (positions or []):
            direction = "BUY" if int(p.type) == 0 else "SELL"
            s_info = sym_info_map.get(p.symbol)
            rem_risk, is_rf = _estimate_position_open_risk(sleeve_key, p, s_info)
            beta = 0.0 if is_rf else get_usd_factor_beta(p.symbol, direction)
            conn.execute(
                """
                INSERT OR REPLACE INTO active_fleet_exposure
                (sleeve, ticket, symbol, direction, risk_usd, usd_beta, is_risk_free, updated_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sleeve_key, int(p.ticket), str(p.symbol), direction, rem_risk, beta, int(is_rf), ts_str),
            )
        conn.commit()
    finally:
        conn.close()

def evaluate_portfolio_heat_gate(
    sleeve_key: str,
    symbol: str,
    direction: str,
    proposed_risk_usd: float,
    now_utc: datetime | None = None,
) -> tuple[bool, str]:
    """
    Checks whether opening `(symbol, direction, proposed_risk_usd)` on `sleeve_key`
    respects fleet-wide USD correlation and dollar risk ceilings.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    stale_cutoff = (now_utc - timedelta(seconds=180)).isoformat()

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT sleeve, ticket, symbol, direction, risk_usd, usd_beta, is_risk_free
            FROM active_fleet_exposure
            WHERE updated_utc >= ? AND is_risk_free = 0
            """,
            (stale_cutoff,),
        ).fetchall()
    finally:
        conn.close()

    # Exclude any stale row from the requesting sleeve (it will be replaced on sync)
    other_rows = [r for r in rows if r[0] != sleeve_key]

    cur_risk_usd = sum(float(r[4]) for r in other_rows)
    cur_net_usd_beta = sum(float(r[5]) for r in other_rows)

    prop_beta = get_usd_factor_beta(symbol, direction)
    new_total_risk = cur_risk_usd + float(proposed_risk_usd)
    new_net_beta = cur_net_usd_beta + prop_beta

    if new_total_risk > (MAX_FLEET_OPEN_RISK_USD + 0.05):
        return False, f"FLEET_RISK_HEAT_CAP (${cur_risk_usd:.2f}+${proposed_risk_usd:.2f} > ${MAX_FLEET_OPEN_RISK_USD:.2f})"

    if abs(new_net_beta) > (MAX_NET_USD_BETA + 1e-6):
        active_desc = ",".join(f"{r[0]}:{r[2]}({r[3]})" for r in other_rows) or "NONE"
        return False, f"USD_CORRELATION_CAP (NetBeta={cur_net_usd_beta:+.1f}->{new_net_beta:+.1f} | Open={active_desc})"

    return True, f"HEAT_OK (FleetRisk=${new_total_risk:.2f}/${MAX_FLEET_OPEN_RISK_USD:.2f} | NetUSDBeta={new_net_beta:+.1f})"

if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    ok, msg = evaluate_portfolio_heat_gate("T1", "BTCUSD", "SELL", 4.50, now)
    print(f"[LIVE HEAT CHECK] Allow={ok} | {msg}")
