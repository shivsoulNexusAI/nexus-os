import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from app.core.config import settings
from app.handlers import chart_handler

# ------------------------------------------------------------------------------
# 1. Logging Setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("QuantumNexus")

# Suppress verbose HTTP network polling logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)


# ------------------------------------------------------------------------------
# 2. Global Exception Interceptor
# ------------------------------------------------------------------------------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches unhandled runtime exceptions and prevents bot worker freezes."""
    logger.error("Exception encountered during update processing:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ *Nexus System Alert:* An unexpected engine error occurred. Check stderr_crash.log.",
            parse_mode="Markdown",
        )


# ------------------------------------------------------------------------------
# 3. Application Factory & Handler Registry
# ------------------------------------------------------------------------------
def main():
    logger.info("⚡ Initializing Quantum Nexus Engine...")

    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None) or getattr(settings, "BOT_TOKEN", None) or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("CRITICAL: TELEGRAM_BOT_TOKEN not resolved in settings or environment!")

    application = ApplicationBuilder().token(bot_token).build()

    # --- Administrative & Diagnostic Command Handlers ---
    application.add_handler(CommandHandler("start", chart_handler.start_command))
    application.add_handler(CommandHandler("position", chart_handler.positions_command))
    application.add_handler(CommandHandler("positions", chart_handler.positions_command))
    application.add_handler(CommandHandler("status", chart_handler.status_command))
    application.add_handler(CommandHandler("export_metrics", chart_handler.export_metrics_command))
    application.add_handler(CommandHandler("panic", chart_handler.panic_command))
    application.add_handler(CommandHandler("restart", chart_handler.restart_command))
    application.add_handler(CommandHandler("reboot", chart_handler.reboot_host_command))
    application.add_handler(CommandHandler("reboot_host", chart_handler.reboot_host_command))

    # --- Vision Pipeline: Chart Ingestion Handler ---
    application.add_handler(MessageHandler(filters.PHOTO, chart_handler.analyze_chart))

    # --- Interactive Callback Gate: Confirm, Dismiss & Emergency Panic Routing ---
    application.add_handler(CallbackQueryHandler(chart_handler.order_button_callback))

    # --- Resilience: Global Error Interceptor ---
    application.add_error_handler(global_error_handler)

    logger.info("🚀 Quantum Nexus Bot Engine is LIVE and polling...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()