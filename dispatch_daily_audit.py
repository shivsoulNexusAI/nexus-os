# =====================================================================
# SHIVSOUL NEXUS v7.0 // DAILY CLOSE AUDIT & TELEGRAM REPORT DISPATCHER
# =====================================================================
import sqlite3
import subprocess
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from telegram import Bot
from telegram.request import HTTPXRequest
from telegram.error import TelegramError, TimedOut, NetworkError
from nexus_tg_config import resolve_telegram_credentials

DB_PATH = Path("nexus_ledger.db")
REPORTS_DIR = Path(r"C:\Quant-Nexus-Eng\reports")
EXPORT_SCRIPT = Path(r"C:\Quant-Nexus-Eng\export_ledger_report.py")
HEALTH_SCRIPT = Path(r"C:\Quant-Nexus-Eng\audit_mt5_health.py")


def build_resilient_bot(token: str) -> Bot:
    request = HTTPXRequest(
        connection_pool_size=4,
        connect_timeout=15.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=15.0,
    )
    return Bot(token=token, request=request)


async def send_with_retry(coro_factory, label: str, max_attempts: int = 3) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            await coro_factory()
            return
        except (TimedOut, NetworkError) as e:
            if attempt == max_attempts:
                raise
            wait_s = 2.0 * attempt
            print(f"[WARN] Telegram {label} transient error (attempt {attempt}/{max_attempts}): {e} — retrying in {wait_s:.0f}s...")
            await asyncio.sleep(wait_s)


def compact_sqlite_wal() -> str:
    """Folds committed WAL frames into nexus_ledger.db and truncates the -wal file safely."""
    if not DB_PATH.exists():
        return "⚠️ `nexus_ledger.db` not found"

    wal_path = Path(f"{DB_PATH}-wal")
    before_bytes = wal_path.stat().st_size if wal_path.exists() else 0

    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        busy, log_frames, ckpt_frames = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
    finally:
        conn.close()

    after_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    status = "TRUNCATED" if busy == 0 else "BUSY_DEFERRED"
    return (
        f"{status} (`{before_bytes / 1024:.1f} KB` -> `{after_bytes / 1024:.1f} KB`, "
        f"frames `{ckpt_frames}/{log_frames}`)"
    )


def build_daily_close_summary(health_excerpt: str, wal_status: str) -> str:
    now_utc = datetime.now(timezone.utc)
    lines = [
        "🏁 *SHIVSOUL NEXUS v7.0 // DAILY CLOSE AUDIT*",
        f"`{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}`\n",
        "*Sleeve Equity & Heartbeats:*",
    ]

    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT sleeve, login, pid, last_tick_utc, equity, status FROM worker_heartbeats ORDER BY sleeve ASC;")
            workers = cur.fetchall()
            total_eq = 0.0
            for w in workers:
                age = (now_utc - datetime.fromisoformat(w["last_tick_utc"])).total_seconds()
                eq = float(w["equity"])
                total_eq += eq
                icon = "🟢" if (w["status"] == "RUNNING" and age < 30.0) else "🔴"
                lines.append(f"{icon} *{w['sleeve']}* (`#{w['login']}`): `${eq:,.2f}` | `{age:.1f}s` ago")

            lines.append(f"\n💰 *Total Fleet Equity:* `${total_eq:,.2f}`")

            cur.execute("SELECT ticket, sleeve, symbol, direction, volume, entry_price FROM managed_positions;")
            positions = cur.fetchall()
            lines.append(f"📌 *Open Positions:* `{len(positions)}`")
            for p in positions:
                lines.append(
                    f"  • `{p['sleeve']}` *{p['symbol']}* `{p['direction']}` `{p['volume']}` @ `{p['entry_price']}` (#{p['ticket']})"
                )

            cutoff_24h = datetime.fromtimestamp(now_utc.timestamp() - 86400, timezone.utc).isoformat()
            cur.execute("SELECT COUNT(*) AS cnt FROM order_intents WHERE state LIKE '%VETO%' AND created_utc >= ?;", (cutoff_24h,))
            veto_24h = cur.fetchone()["cnt"]
            lines.append(f"🛡️ *24h Execution Vetoes:* `{veto_24h}`")
            lines.append(f"🗄️ *SQLite WAL Checkpoint:* {wal_status}")
        finally:
            conn.close()
    else:
        lines.append("⚠️ `nexus_ledger.db` not found.")

    if health_excerpt:
        lines.append(f"\n*MT5 Bridge Health Snapshot:*\n```\n{health_excerpt}\n```")

    return "\n".join(lines)


async def run_daily_audit() -> None:
    token, chat_id, source = resolve_telegram_credentials(Path("."))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    started_ts = datetime.now(timezone.utc).timestamp() - 1.0

    # 1. Run CSV ledger exporter
    if EXPORT_SCRIPT.exists():
        res = subprocess.run(["python", str(EXPORT_SCRIPT)], capture_output=True, text=True)
        print(res.stdout.strip())
        if res.stderr.strip():
            print(res.stderr.strip())

    # 2. Run MT5 multi-sleeve bridge health audit
    health_lines = []
    if HEALTH_SCRIPT.exists():
        h_res = subprocess.run(["python", str(HEALTH_SCRIPT)], capture_output=True, text=True)
        for line in h_res.stdout.splitlines():
            s = line.strip()
            if s.startswith((">>> AUDITING", "[OK]", "[ERR]", "[ACCOUNT]", "[POSITIONS]")):
                health_lines.append(s)

    # 3. Compact & truncate SQLite WAL file safely
    wal_status = compact_sqlite_wal()
    print(f"[OK] SQLite WAL Checkpoint: {wal_status}")

    summary_text = build_daily_close_summary("\n".join(health_lines[:18]), wal_status)
    print("\n--- DAILY AUDIT TELEGRAM PAYLOAD ---")
    print(summary_text)

    if not token or not chat_id:
        print(f"[ERR] Missing Telegram credentials (source={source}); skipping Telegram push.")
        return

    # 4. Collect newly exported CSVs from this run
    csv_files = sorted(REPORTS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    fresh_csvs = [p for p in csv_files if p.stat().st_mtime >= started_ts and p.stat().st_size > 0]

    try:
        bot = build_resilient_bot(token)
        async with bot:
            await send_with_retry(
                lambda: bot.send_message(
                    chat_id=chat_id,
                    text=summary_text,
                    parse_mode="Markdown",
                ),
                label="send_message",
            )
            for csv_path in fresh_csvs[:4]:
                row_count = max(0, len(csv_path.read_text(encoding="utf-8", errors="replace").splitlines()) - 1)

                async def _upload(p=csv_path, rc=row_count):
                    with p.open("rb") as fh:
                        await bot.send_document(
                            chat_id=chat_id,
                            document=fh,
                            filename=p.name,
                            caption=f"📄 Daily Close Export: `{p.name}` ({rc} records)",
                            parse_mode="Markdown",
                        )

                await send_with_retry(_upload, label=f"send_document({csv_path.name})")
            print(f"[SUCCESS] Dispatched daily close summary and {len(fresh_csvs)} CSV file(s) to Chat ID {chat_id}.")
    except TelegramError as e:
        print(f"[ERR] Telegram API rejected daily audit dispatch: {e}")
    except Exception as e:
        print(f"[ERR] Unexpected daily audit dispatch failure: {e}")


if __name__ == "__main__":
    asyncio.run(run_daily_audit())
