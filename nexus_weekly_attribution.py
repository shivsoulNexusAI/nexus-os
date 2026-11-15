import json
import sqlite3
import httpx
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ==============================================================================
# QUANTNEXUS // SUNDAY WEEKLY ATTRIBUTION & SLIPPAGE AUDIT ENGINE (v5.0)
# ==============================================================================
BASE_DIR         = Path(r"C:\Quant-Nexus-Eng")
DB_PATH          = BASE_DIR / "nexus_ledger.db"
REPORT_DIR       = BASE_DIR / "audit_reports"
NEXUS_TG_CONFIG  = BASE_DIR / "telegram_nexus_config.json"
FALLBACK_CONFIG  = BASE_DIR / "t1_telegram_config.json"
VERIFIED_T1_PATH = r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe"
MAGIC_NUMBER     = 278062038

def load_nexus_bot():
    cfg_path = NEXUS_TG_CONFIG if NEXUS_TG_CONFIG.exists() else FALLBACK_CONFIG
    data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    token = data.get("token", data.get("bot_token", data.get("", "")))
    chat_id = str(data.get("chat_id", data.get("authorized_chat_id", "5279761713")))
    return token, chat_id

def send_nexus_report(text: str):
    token, chat_id = load_nexus_bot()
    if not token or not chat_id:
        print("[WARN] Missing Nexus AI Bot credentials.")
        return
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=12.0,
        )
        print(f"[TELEGRAM] Sent weekly attribution report (HTTP {resp.status_code})")
    except Exception as e:
        print(f"[TELEGRAM ERR] {e}")

def classify_session(dt_utc: datetime) -> str:
    hr = dt_utc.hour
    if 7 <= hr <= 10:
        return "London KZ"
    elif 12 <= hr <= 16:
        return "NY-LDN Ovlp"
    elif 0 <= hr <= 3:
        return "Asia KZ"
    return "Off-Peak"

def run_weekly_audit(lookback_days: int = 7):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=lookback_days)

    # 1. Query SQLite execution telemetry (Slippage, Latency, VPIN, Order Mode)
    exec_rows = []
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM executions
            WHERE ts_utc >= ?
            ORDER BY id ASC
        """, (start_utc.isoformat(),))
        exec_rows = [dict(r) for r in cur.fetchall()]
        conn.close()

    # 2. Pull realized closed deals across all 3 Tripartite Sleeves (T1, T2, T3)
    realized_deals = []
    acc_balance, acc_equity = 0.0, 0.0
    silos = [
        ("T1", r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe", 278062038, r"H@ngkook3695", "Exness-MT5Trial5"),
        ("T2", r"C:\MT5_Pending_278041169\terminal64.exe", 278062039, r"H@ngkook3695", "Exness-MT5Trial5"),
        ("T3", r"C:\MT5_HFT_278041671\terminal64.exe", 278062042, r"H@ngkook3695", "Exness-MT5Trial5"),
    ]
    for s_id, s_path, s_login, s_pwd, s_srv in silos:
        if mt5.initialize(path=s_path, login=s_login, password=s_pwd, server=s_srv):
            acc = mt5.account_info()
            if acc:
                acc_balance += acc.balance
                acc_equity += acc.equity
            deals = mt5.history_deals_get(start_utc, now_utc) or []
            for d in deals:
                if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY):
                    net_pnl = float(d.profit + d.commission + d.swap)
                    realized_deals.append({
                        "sleeve": s_id,
                        "ticket": d.ticket,
                        "position_id": d.position_id,
                        "symbol": d.symbol,
                        "volume": d.volume,
                        "price": d.price,
                        "net_pnl": net_pnl,
                        "time_utc": datetime.fromtimestamp(d.time, tz=timezone.utc),
                        "comment": d.comment,
                    })
            mt5.shutdown()

    # Map execution metadata by ticket/order ID for attribution
    exec_by_ticket = {int(r["ticket"]): r for r in exec_rows if r.get("ticket")}

    # 3. Aggregate Realized Performance & Attribution Buckets
    wins = [d["net_pnl"] for d in realized_deals if d["net_pnl"] > 0]
    losses = [abs(d["net_pnl"]) for d in realized_deals if d["net_pnl"] < 0]
    be_count = sum(1 for d in realized_deals if abs(d["net_pnl"]) < 0.05)

    gross_win = sum(wins)
    gross_loss = sum(losses)
    net_total = sum(d["net_pnl"] for d in realized_deals)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.9 if gross_win > 0 else 0.0)
    win_rate = (len(wins) / max(1, len(wins) + len(losses))) * 100.0
    expectancy = net_total / max(1, len(realized_deals))

    # Per-Symbol Attribution
    sym_stats = {}
    for d in realized_deals:
        s = d["symbol"]
        st = sym_stats.setdefault(s, {"trades": 0, "wins": 0, "pnl": 0.0, "gp": 0.0, "gl": 0.0})
        st["trades"] += 1
        st["pnl"] += d["net_pnl"]
        if d["net_pnl"] > 0:
            st["wins"] += 1
            st["gp"] += d["net_pnl"]
        elif d["net_pnl"] < 0:
            st["gl"] += abs(d["net_pnl"])

    # Session Attribution
    sess_stats = {}
    for d in realized_deals:
        meta = exec_by_ticket.get(d["position_id"])
        entry_dt = datetime.fromisoformat(meta["ts_utc"]) if meta else d["time_utc"]
        sess = classify_session(entry_dt)
        ss = sess_stats.setdefault(sess, {"trades": 0, "pnl": 0.0})
        ss["trades"] += 1
        ss["pnl"] += d["net_pnl"]

    # 4. Execution Quality, Slippage & FVG Passive Limit Router Audit
    filled_execs = [r for r in exec_rows if r.get("status") == "FILLED"]
    fvg_execs    = [r for r in exec_rows if r.get("order_mode") == "FVG_LIMIT"]
    mkt_execs    = [r for r in exec_rows if r.get("order_mode") == "MARKET"]

    slippages = [float(r.get("slippage_pts", 0.0)) for r in filled_execs]
    latencies = [float(r.get("latency_ms", 0.0)) for r in filled_execs if float(r.get("latency_ms", 0.0)) > 0]
    vp_scores = [float(r.get("vpin", 0.0)) for r in exec_rows if float(r.get("vpin", 0.0)) > 0]

    avg_slip = float(np.mean(slippages)) if slippages else 0.0
    max_slip = float(np.max(np.abs(slippages))) if slippages else 0.0
    avg_lat  = float(np.mean(latencies)) if latencies else 0.0
    p95_lat  = float(np.percentile(latencies, 95)) if latencies else 0.0
    avg_vpin = float(np.mean(vp_scores)) if vp_scores else 0.0

    # Slippage breakdown per symbol
    slip_by_sym = {}
    for r in filled_execs:
        s = r["symbol"]
        slip_by_sym.setdefault(s, []).append(float(r.get("slippage_pts", 0.0)))

    # 5. Format Executive Telegram Report for Nexus AI Bot
    sym_lines = []
    for s, st in sorted(sym_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
        pf_s = (st["gp"] / st["gl"]) if st["gl"] > 0 else (9.99 if st["gp"] > 0 else 0.0)
        wr_s = (st["wins"] / max(1, st["trades"])) * 100.0
        sym_lines.append(f"• {s:<6}: {st['pnl']:+7.2f}$ | PF {pf_s:.2f} | WR {wr_s:.0f}% ({st['trades']}tr)")
    if not sym_lines:
        sym_lines.append("• No closed deals recorded in trailing 7d window")

    sess_lines = [
        f"• {k:<11}: {v['pnl']:+7.2f}$ ({v['trades']} exits)"
        for k, v in sorted(sess_stats.items(), key=lambda x: x[1]["pnl"], reverse=True)
    ] or ["• Awaiting first weekly session sample"]

    slip_lines = [
        f"• {s:<6}: Avg {np.mean(vals):+.1f} pts | Max {np.max(np.abs(vals)):.1f} pts ({len(vals)} fills)"
        for s, vals in slip_by_sym.items()
    ] or ["• Clean baseline (0 market fills in window)"]

    # Automated Quant Calibration Advisory
    advisories = []
    if max_slip > 15.0:
        advisories.append("⚠️ Elevated slippage detected -> Favor FVG_LIMIT passive routing")
    if len(realized_deals) >= 10 and profit_factor < 1.15:
        advisories.append("⚠️ PF < 1.15 -> Consider tightening Gate from 82% to 85%")
    if not advisories:
        advisories.append("✅ Execution latency, slippage & PF within institutional bounds")

    period_str = f"{start_utc.strftime('%b %d')} -> {now_utc.strftime('%b %d, %Y')}"
    report_msg = (
        f"📊 QUANTNEXUS // SUNDAY WEEKLY ATTRIBUTION & SLIPPAGE AUDIT\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Period : {period_str}\n"
        f"Fleet  : T1+T2+T3 Tripartite | NAV ${acc_balance:,.2f} | Eq ${acc_equity:,.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 REALIZED PERFORMANCE (7-DAY)\n"
        f"Net P&L      : ${net_total:+,.2f} (Exp: ${expectancy:+.2f}/exit)\n"
        f"Profit Factor: {profit_factor:.2f} | Win Rate: {win_rate:.1f}%\n"
        f"Exits Audit  : {len(wins)}W / {len(losses)}L / {be_count} BE\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏛️ ASSET ATTRIBUTION\n"
        + "\n".join(sym_lines) + "\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 CHRONOS SESSION ATTRIBUTION\n"
        + "\n".join(sess_lines) + "\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ EXECUTION & SLIPPAGE TELEMETRY (nexus_ledger.db)\n"
        f"Router Split : {len(mkt_execs)} Market | {len(fvg_execs)} FVG-Limit\n"
        f"Slippage     : Avg {avg_slip:+.1f} pts | Worst {max_slip:.1f} pts\n"
        f"Fill Latency : Avg {avg_lat:.1f} ms | P95 {p95_lat:.1f} ms\n"
        f"Mean tVPIN   : {avg_vpin:.2f}\n"
        + "\n".join(slip_lines) + "\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 QUANT ADVISORY\n"
        + "\n".join(advisories)
    )

    # Save archival JSON & Markdown report locally
    stamp = now_utc.strftime("%Y%m%d_%H%MUTC")
    (REPORT_DIR / f"weekly_audit_{stamp}.md").write_text(report_msg, encoding="utf-8")
    (REPORT_DIR / f"weekly_audit_{stamp}.json").write_text(
        json.dumps({
            "period": period_str,
            "net_pnl": round(net_total, 2),
            "profit_factor": round(profit_factor, 2),
            "win_rate": round(win_rate, 1),
            "avg_slippage_pts": round(avg_slip, 2),
            "avg_latency_ms": round(avg_lat, 1),
            "assets": sym_stats,
            "sessions": sess_stats,
        }, indent=2),
        encoding="utf-8",
    )

    print(report_msg)
    send_nexus_report(report_msg + '\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n' + build_strategy_attribution_block())


def build_strategy_attribution_block(db_path: str = r"C:\Quant-Nexus-Eng\nexus_ledger.db") -> str:
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(executions)").fetchall()]
        if "strategy" not in cols:
            conn.close()
            return "📊 STRATEGY ATTRIBUTION: Pending first multi-strategy fill"
        rows = conn.execute("""
            SELECT COALESCE(strategy, 'SWEEP_VP') AS strat,
                   COUNT(*) AS trades,
                   ROUND(AVG(confidence), 1) AS avg_conf,
                   ROUND(AVG(slippage_pts), 1) AS avg_slip
            FROM executions
            GROUP BY COALESCE(strategy, 'SWEEP_VP')
            ORDER BY trades DESC
        """).fetchall()
        conn.close()
        if not rows:
            return "📊 STRATEGY ATTRIBUTION (OB+IFVG vs SWEEP_VP): 0 fills logged yet"
        lines = ["📊 STRATEGY ATTRIBUTION (OB+IFVG vs SWEEP_VP)"]
        for strat, cnt, avg_c, avg_s in rows:
            lines.append(f"  • {strat}: {cnt} trades | AvgConf {avg_c}% | AvgSlip {avg_s:+.1f}pt")
        return "\n".join(lines)
    except Exception as ex:
        return f"📊 STRATEGY ATTRIBUTION ERR: {ex}"


if __name__ == "__main__":
    run_weekly_audit(lookback_days=7)
