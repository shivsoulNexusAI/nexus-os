import os
import io
import csv
import sys
import time
import uuid
import logging
import asyncio
import sqlite3
import traceback
from datetime import datetime
from typing import Dict, Any

import httpx
import psutil
import MetaTrader5 as mt5
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.agents.oracle import OracleAgent
from app.agents.nexus import NexusAgent
from app.core.config import settings

logger = logging.getLogger(__name__)

oracle_agent = OracleAgent()
nexus_agent = NexusAgent()

BOT_START_TIME = time.time()
MAGIC_NUMBER = 999101
DB_PATH = os.path.join(r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot", "quant_metrics.db")
MT5_BRIDGE_URL = getattr(settings, "MT5_BRIDGE_URL", os.getenv("MT5_BRIDGE_URL", "http://127.0.0.1:5000/webhook"))


# ------------------------------------------------------------------------------
# 1. MT5 Helper Execution (Threaded Safe)
# ------------------------------------------------------------------------------
def _sync_fetch_positions_data():
    if not mt5.initialize():
        return {"error": f"Failed to connect to MT5: {mt5.last_error()}"}

    pending = mt5.orders_get(magic=MAGIC_NUMBER) or []
    positions = mt5.positions_get(magic=MAGIC_NUMBER) or []

    pending_list = []
    for o in pending:
        t_str = "BUY_LIMIT" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else "SELL_LIMIT"
        pending_list.append({
            "ticket": o.ticket,
            "symbol": o.symbol,
            "type": t_str,
            "lots": o.volume_current,
            "price": o.price_open,
            "sl": o.sl,
            "tp": o.tp
        })

    pos_list = []
    for p in positions:
        p_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        pos_list.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": p_type,
            "lots": p.volume,
            "open": p.price_open,
            "current": p.price_current,
            "profit": round(p.profit, 2),
            "sl": p.sl,
            "tp": p.tp
        })

    return {
        "pending": pending_list,
        "positions": pos_list,
        "error": None
    }


def _sync_fetch_host_telemetry():
    process = psutil.Process()
    process_memory_mb = process.memory_info().rss / (1024 * 1024)
    for child in process.children(recursive=True):
        process_memory_mb += child.memory_info().rss / (1024 * 1024)

    sys_ram = psutil.virtual_memory()
    sys_cpu = psutil.cpu_percent(interval=None)
    return {
        "process_ram": process_memory_mb,
        "sys_ram_pct": sys_ram.percent,
        "sys_cpu": sys_cpu
    }


# ------------------------------------------------------------------------------
# 2. Database with Auto-Migration & HTTP Bridge Dispatchers
# ------------------------------------------------------------------------------
async def dispatch_mt5_order(order_payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(MT5_BRIDGE_URL, json=order_payload)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def dispatch_mt5_panic() -> dict:
    panic_url = MT5_BRIDGE_URL.replace("/webhook", "/panic")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(panic_url)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


class PersistentMetricsTracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_and_migrate_db()

    def _init_and_migrate_db(self):
        """Creates table and auto-migrates missing columns if database exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    asset TEXT,
                    direction TEXT,
                    rrr REAL,
                    quant_score REAL,
                    executed INTEGER DEFAULT 0,
                    ticket INTEGER DEFAULT 0
                )
            """)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(signal_history)")
            existing_columns = [col[1] for col in cursor.fetchall()]

            if "executed" not in existing_columns:
                cursor.execute("ALTER TABLE signal_history ADD COLUMN executed INTEGER DEFAULT 0")
            if "ticket" not in existing_columns:
                cursor.execute("ALTER TABLE signal_history ADD COLUMN ticket INTEGER DEFAULT 0")
            conn.commit()

    async def record_signal(self, asset: str, direction: str, rrr: float, quant_score: float) -> int:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_record, asset, direction, rrr, quant_score)

    def _sync_record(self, asset: str, direction: str, rrr: float, quant_score: float) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO signal_history (timestamp, asset, direction, rrr, quant_score, executed, ticket)
                VALUES (?, ?, ?, ?, ?, 0, 0)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                asset.upper().strip(),
                direction.upper().strip(),
                float(rrr),
                float(quant_score)
            ))
            conn.commit()
            return cur.lastrowid

    async def mark_executed(self, db_id: int, ticket: int):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_mark_executed, db_id, ticket)

    def _sync_mark_executed(self, db_id: int, ticket: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE signal_history SET executed = 1, ticket = ? WHERE id = ?", (ticket, db_id))
            conn.commit()

    async def get_summary(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_get_summary)

    def _sync_get_summary(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), AVG(rrr) FROM signal_history WHERE rrr > 0")
            row = cursor.fetchone()
            total_charts = row[0] or 0
            avg_rrr = row[1] or 0.0

            cursor.execute("SELECT COUNT(*) FROM signal_history WHERE direction LIKE '%LONG%' OR direction LIKE '%BUY%'")
            longs = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM signal_history WHERE direction LIKE '%SHORT%' OR direction LIKE '%SELL%'")
            shorts = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM signal_history WHERE direction LIKE '%HOLD%' OR direction LIKE '%WAIT%'")
            holds = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM signal_history WHERE executed = 1")
            executed_count = cursor.fetchone()[0]

            cursor.execute("SELECT asset, COUNT(*) as c FROM signal_history GROUP BY asset ORDER BY c DESC LIMIT 1")
            top_asset_row = cursor.fetchone()
            top_asset = top_asset_row[0] if top_asset_row else "None"

            return {
                "total_charts": total_charts,
                "executed_orders": executed_count,
                "long_signals": longs,
                "short_signals": shorts,
                "hold_signals": holds,
                "avg_rrr": avg_rrr,
                "top_asset": top_asset
            }

    async def export_csv_data(self) -> io.BytesIO:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_export_csv)

    def _sync_export_csv(self) -> io.BytesIO:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signal_history ORDER BY id ASC")
            rows = cursor.fetchall()
            headers = ["ID", "Timestamp", "Asset", "Direction", "RRR", "Quant_Score", "Executed", "Ticket"]

            string_buffer = io.StringIO()
            writer = csv.writer(string_buffer)
            writer.writerow(headers)
            writer.writerows(rows)

            byte_buffer = io.BytesIO(string_buffer.getvalue().encode("utf-8"))
            byte_buffer.name = f"quant_nexus_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            byte_buffer.seek(0)
            return byte_buffer


metrics_tracker = PersistentMetricsTracker()


def format_duration(seconds: float) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


# ------------------------------------------------------------------------------
# 3. Safe Telegram Messaging (Splits messages > 3800 chars)
# ------------------------------------------------------------------------------
async def send_chunked_message(update: Update, text: str):
    MAX_CHUNK = 3800
    if len(text) <= MAX_CHUNK:
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    lines = text.split("\n")
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > MAX_CHUNK:
            await update.message.reply_text("\n".join(current_chunk), parse_mode="Markdown")
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len

    if current_chunk:
        await update.message.reply_text("\n".join(current_chunk), parse_mode="Markdown")


# ------------------------------------------------------------------------------
# 4. Administrative Command Handlers
# ------------------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "⚡ *Quantum Nexus Vision & Algo Engine Online*\n\n"
        "• Drop trading charts for instant zero-touch execution\n"
        "• `/positions` - Query all live MT5 trades and pending orders\n"
        "• `/status` - Host telemetry and performance metrics\n"
        "• `/export_metrics` - Download trade history as CSV\n"
        "• `/panic` - Liquidate open positions & cancel orders\n"
        "• `/reboot` - Remote Windows host machine power restart"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = await asyncio.to_thread(_sync_fetch_positions_data)

        if data.get("error"):
            await update.message.reply_text(f"⚠️ *MT5 Access Error:* `{data['error']}`", parse_mode="Markdown")
            return

        pending = data["pending"]
        positions = data["positions"]

        lines = ["📊 *LIVE MT5 EXECUTIONS (Magic #999101)*", "━━━━━━━━━━━━━━━━━━━━"]

        # Pending Orders
        if pending:
            lines.append(f"⏳ *PENDING ORDERS ({len(pending)} total):*")
            for o in pending[:10]:
                lines.append(
                    f"• `#{o['ticket']}` | *{o['symbol']}* ({o['type']})\n"
                    f"  Price: `{o['price']}` | Lots: `{o['lots']}` | SL: `{o['sl']}` | TP: `{o['tp']}`"
                )
            if len(pending) > 10:
                lines.append(f"*(...and {len(pending) - 10} more pending orders)*")
            lines.append("────────────────────")
        else:
            lines.append("⏳ *Pending Orders:* `None`")

        # Open Positions
        total_pnl = 0.0
        if positions:
            lines.append(f"\n📈 *OPEN POSITIONS ({len(positions)} total):*")
            for p in positions[:10]:
                total_pnl += p["profit"]
                lines.append(
                    f"• `#{p['ticket']}` | *{p['symbol']}* ({p['type']})\n"
                    f"  Open: `{p['open']}` | Current: `{p['current']}`\n"
                    f"  Lots: `{p['lots']}` | PnL: `${p['profit']:+.2f}`"
                )
            if len(positions) > 10:
                total_pnl += sum(p["profit"] for p in positions[10:])
                lines.append(f"*(...and {len(positions) - 10} more open positions)*")
            lines.append("────────────────────")
            lines.append(f"💰 *Total Floating PnL:* `${total_pnl:+,.2f}`")
        else:
            lines.append("📈 *Open Positions:* `None in market`")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📅 *Updated:* `{datetime.now().strftime('%H:%M:%S UTC')}`")

        await send_chunked_message(update, "\n".join(lines))

    except Exception as exc:
        logger.error(f"Error in /positions: {traceback.format_exc()}")
        await update.message.reply_text(f"⚠️ *Positions Error:* `{str(exc)}`", parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        host = await asyncio.to_thread(_sync_fetch_host_telemetry)
        uptime_str = format_duration(time.time() - BOT_START_TIME)
        perf = await metrics_tracker.get_summary()

        status_report = (
            "💓 *Quant Nexus On-Demand Telemetry*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 *Timestamp:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"⏱️ *Engine Uptime:* `{uptime_str}`\n\n"
            "📈 *DATABASE METRICS:*\n"
            f"• *Total Setups Recorded:* `{perf['total_charts']}`\n"
            f"• *Live MT5 Executions:* `{perf['executed_orders']}`\n"
            f"• *Average Setup RRR:* `1:{perf['avg_rrr']:.2f}`\n"
            f"• *Bias:* `🟢 {perf['long_signals']} L | 🔴 {perf['short_signals']} S | ⏸️ {perf['hold_signals']} H`\n"
            f"• *Dominant Asset:* `{perf['top_asset']}`\n\n"
            "📊 *HOST SYSTEM:*\n"
            f"• *RAM Allocation:* `{host['process_ram']:.1f} MB` (System: `{host['sys_ram_pct']}%`)\n"
            f"• *CPU Load:* `{host['sys_cpu']}%`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ *Zero-Touch STP Vision & Algo Bridge Operational.*"
        )
        await update.message.reply_text(status_report, parse_mode="Markdown")

    except Exception as exc:
        logger.error(f"Error in /status: {traceback.format_exc()}")
        await update.message.reply_text(f"⚠️ *Status Error:* `{str(exc)}`", parse_mode="Markdown")


async def export_metrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("📊 *Compiling quantitative database ledger...*", parse_mode="Markdown")
    try:
        csv_file = await metrics_tracker.export_csv_data()
        perf = await metrics_tracker.get_summary()

        caption = (
            "📈 *Quant Nexus Analytical Audit Ledger*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 *Exported At:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"• *Total Setups Recorded:* `{perf['total_charts']}`\n"
            f"• *MT5 Executed Trades:* `{perf['executed_orders']}`\n"
            f"• *Average Setup RRR:* `1:{perf['avg_rrr']:.2f}`\n"
            f"• *Dominant Asset:* `{perf['top_asset']}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📁 *Format:* RFC 4180 CSV"
        )

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_file,
            filename=csv_file.name,
            caption=caption,
            parse_mode="Markdown"
        )
        await status_msg.delete()
    except Exception as exc:
        await status_msg.edit_text(f"⚠️ *Export Error:* {str(exc)}", parse_mode="Markdown")


async def panic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🚨 EXECUTE EMERGENCY FLUSH 🚨", callback_data="panic_confirm_now"),
            InlineKeyboardButton("Abort", callback_data="panic_abort")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ *EMERGENCY PANIC BRAKE TRIGGERED*\n\n"
        "This will instantly:\n"
        "• Market-close **ALL** open positions.\n"
        "• Cancel **ALL** pending orders on Exness MT5.\n\n"
        "Are you certain?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def reboot_host_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command initiating the remote Windows host reboot confirmation dialog."""
    user_id = str(update.effective_user.id)
    admin_id = str(getattr(settings, "ADMIN_TELEGRAM_ID", os.getenv("ADMIN_TELEGRAM_ID", ""))).strip()

    if admin_id and user_id != admin_id:
        await update.message.reply_text("⛔ *Unauthorized:* Restricted host control command.", parse_mode="Markdown")
        return

    keyboard = [
        [
            InlineKeyboardButton("🔄 REBOOT HOST PC NOW", callback_data="reboot_host_confirm"),
            InlineKeyboardButton("Cancel", callback_data="reboot_host_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ *REMOTE HOST MACHINE REBOOT INITIATED*\n\n"
        "This command will:\n"
        "• Gracefully flush pending processes\n"
        "• Force-restart the physical Windows host machine (`shutdown /r /t 5`)\n"
        "• Automatically restart the Tri-Process stack on system reboot\n\n"
        "Are you certain?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 *Reboot Initiated:* Supervisor will recover...", parse_mode="Markdown")
    await asyncio.sleep(1)
    sys.exit(1)


# ------------------------------------------------------------------------------
# 5. Zero-Touch STP Vision Pipeline
# ------------------------------------------------------------------------------
async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = await update.message.reply_text(
        "⚡ *Quantum Vision Engaged: Analyzing chart for instant execution...*", 
        parse_mode="Markdown"
    )

    try:
        photo = update.message.photo[-1]
        file_obj = await context.bot.get_file(photo.file_id)
        image_bytes = await file_obj.download_as_bytearray()

        oracle_result = await oracle_agent.identify_and_analyze(bytes(image_bytes))
        quant_signal = await nexus_agent.synthesize(oracle_data=oracle_result)

        db_id = await metrics_tracker.record_signal(
            asset=quant_signal.asset,
            direction=quant_signal.direction,
            rrr=quant_signal.risk_reward_ratio,
            quant_score=quant_signal.quant_score
        )

        direction_clean = quant_signal.direction.upper()
        execution_report = quant_signal.telegram_formatted_report

        if "HOLD" in direction_clean or "WAIT" in direction_clean:
            await status_message.edit_text(
                execution_report + "\n\n⏸️ *Auto-Execution Skipped:* Neutral or non-actionable setup.",
                parse_mode="Markdown"
            )
            return

        MIN_CONVICTION_SCORE = 6.5
        MIN_RRR = 1.5

        if quant_signal.quant_score < MIN_CONVICTION_SCORE or quant_signal.risk_reward_ratio < MIN_RRR:
            await status_message.edit_text(
                execution_report + 
                f"\n\n⚠️ *Auto-Execution Vetoed by Risk Gate:*\n"
                f"• Score: `{quant_signal.quant_score}/{MIN_CONVICTION_SCORE}`\n"
                f"• RRR: `1:{quant_signal.risk_reward_ratio:.2f}` (Min: `1:{MIN_RRR}`)",
                parse_mode="Markdown"
            )
            return

        order_dict = (
            quant_signal.webhook_order.model_dump()
            if hasattr(quant_signal.webhook_order, "model_dump")
            else quant_signal.webhook_order
        )

        bridge_res = await dispatch_mt5_order(order_dict)

        if bridge_res.get("success"):
            ticket = bridge_res["data"].get("ticket", "LIVE")
            symbol = bridge_res["data"].get("symbol", order_dict.get("symbol"))
            await metrics_tracker.mark_executed(db_id, ticket if isinstance(ticket, int) else 0)

            final_text = (
                execution_report +
                f"\n\n⚡ *AUTO-EXECUTION COMPLETE:*\n"
                f"• *Ticket:* `#{ticket}`\n"
                f"• *Symbol:* `{symbol}`\n"
                f"• *Status:* `Pending Limit Placed on MT5`\n"
                f"• *Trailing Guard:* `1.5R Breakeven + TP1 (50%) Active`"
            )
        else:
            final_text = (
                execution_report +
                f"\n\n❌ *BRIDGE EXECUTION ERROR:*\n"
                f"• *Error:* `{bridge_res.get('error')}`"
            )

        await status_message.edit_text(final_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Quantum Analysis Failed: {e}", exc_info=True)
        await status_message.edit_text(f"⚠️ *Nexus Error:* {str(e)}", parse_mode="Markdown")


# ------------------------------------------------------------------------------
# 6. Callback Query Router (Panic & Reboot Handlers)
# ------------------------------------------------------------------------------
async def order_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        user_id = str(update.effective_user.id)
        admin_id = str(getattr(settings, "ADMIN_TELEGRAM_ID", os.getenv("ADMIN_TELEGRAM_ID", ""))).strip()

        if admin_id and user_id != admin_id:
            await query.answer("⛔ Unauthorized operator.", show_alert=True)
            return

        # --- Reboot Callbacks ---
        if data == "reboot_host_cancel":
            await query.edit_message_text("🛡️ Host Reboot Aborted: System remains running.")
            return

        if data == "reboot_host_confirm":
            await query.edit_message_text(
                "🔄 HOST REBOOT IN PROGRESS\n\n"
                "Executing system restart in 5 seconds...\n"
                "The supervisor will resume operations automatically upon Windows logon."
            )
            sys.stdout.flush()
            os.system('shutdown.exe /r /t 5 /f /c "Remote reboot triggered by Quant Nexus Telegram Bot"')
            return

        # --- Panic Callbacks ---
        if data == "panic_abort":
            await query.edit_message_text("🛡️ Panic Action Aborted: Portfolios remain unchanged.")
            return

        if data == "panic_confirm_now":
            await query.edit_message_text("🚨 EXECUTING EMERGENCY LIQUIDATION...")
            res = await dispatch_mt5_panic()

            if res.get("success"):
                p_data = res.get("data", {})
                report = (
                    "🚨 PANIC FLUSH COMPLETED\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"• Market Positions Closed: {p_data.get('positions_closed', 0)}\n"
                    f"• Pending Orders Purged: {p_data.get('orders_cancelled', 0)}\n"
                    f"• Execution Errors: {len(p_data.get('errors', []))}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "🛡️ Terminal has been flattened into 100% Cash."
                )
            else:
                report = f"⚠️ PANIC FAILED: {res.get('error', 'Unknown bridge error')}"

            await query.edit_message_text(report)
            return

    except Exception as exc:
        logger.error(f"Error in order_button_callback: {traceback.format_exc()}")
        await query.edit_message_text(f"⚠️ Callback Execution Error: {str(exc)}")


handle_chart_image = analyze_chart