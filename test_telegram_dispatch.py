# =====================================================================
# SHIVSOUL NEXUS v7.0 // TELEGRAM BOT CONNECTIVITY & FLEET SUMMARY TEST
# =====================================================================
import sqlite3
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from telegram import Bot
from telegram.error import TelegramError
from nexus_tg_config import resolve_telegram_credentials

DB_PATH = Path("nexus_ledger.db")


def build_fleet_summary() -> str:
    now_utc = datetime.now(timezone.utc)
    lines = [
        "📊 *SHIVSOUL NEXUS v7.0 // LIVE FLEET TELEMETRY*",
        f"`{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}`\n",
        "*Worker Heartbeats:*",
    ]

    if not DB_PATH.exists():
        lines.append("⚠️ `nexus_ledger.db` not found.")
        return "\n".join(lines)

    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT sleeve, pid, last_tick_utc, equity, status FROM worker_heartbeats ORDER BY sleeve ASC;")
    workers = cursor.fetchall()
    total_equity = 0.0

    for w in workers:
        age = (now_utc - datetime.fromisoformat(w["last_tick_utc"])).total_seconds()
        eq = float(w["equity"])
        total_equity += eq
        icon = "🟢" if (w["status"] == "RUNNING" and age < 30.0) else "🔴"
        lines.append(f"{icon} *{w['sleeve']}* (PID `{w['pid']}`): `${eq:,.2f}` | `{age:.1f}s` ago")

    lines.append(f"\n💰 *Total Fleet Equity:* `${total_equity:,.2f}`")

    cursor.execute("SELECT ticket, sleeve, symbol, direction, volume, entry_price FROM managed_positions;")
    positions = cursor.fetchall()
    lines.append(f"\n*Active Positions ({len(positions)}):*")
    if positions:
        for p in positions:
            lines.append(f"• `{p['sleeve']}` | *{p['symbol']}* `{p['direction']}` `{p['volume']}` @ `{p['entry_price']}` (#{p['ticket']})")
    else:
        lines.append("• None (All sleeves flat)")

    conn.close()
    return "\n".join(lines)


async def test_dispatch() -> None:
    token, chat_id, source = resolve_telegram_credentials(Path("."))

    if not token or not chat_id:
        json_files = [p.name for p in Path(".").glob("*.json")]
        print(f"[ERR] Could not resolve Telegram credentials from JSON files: {json_files}")
        return

    print(f"[OK] Loaded Telegram credentials from: {source} (Chat ID: {chat_id})")
    summary_text = build_fleet_summary()
    print("--- GENERATED PAYLOAD ---")
    print(summary_text)
    print("-------------------------\n")

    try:
        bot = Bot(token=token)
        async with bot:
            me = await bot.get_me()
            print(f"[OK] Authenticated as @{me.username} (ID: {me.id})")
            msg = await bot.send_message(
                chat_id=chat_id,
                text=summary_text,
                parse_mode="Markdown",
            )
            print(f"[SUCCESS] Fleet summary pushed to Chat ID {chat_id} (Message ID: {msg.message_id})")
    except TelegramError as e:
        print(f"[ERR] Telegram API rejected dispatch: {e}")
    except Exception as e:
        print(f"[ERR] Unexpected dispatch failure: {e}")


if __name__ == "__main__":
    asyncio.run(test_dispatch())
