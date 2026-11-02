code = """import logging
from telegram import Update
from telegram.ext import ContextTypes
from app.core.security import SecurityLayer
from app.agents.orchestrator import quantum_engine
from app.models.user import get_user_tier

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_msg = (
        f"👁️‍🗨️ *Welcome to the Quantum Nexus, {user.first_name}.*\\n\\n"
        "I am the autonomous AI intelligence for the Shivsoul Nexus Ecosystem.\\n\\n"
        "📸 *Upload a chart image* and I will perform:\\n"
        "• Blind Asset Recognition & Timeframe Detection\\n"
        "• SMC, ICT, and CRT Structural Analysis\\n"
        "• Volume Profile & Order Flow Synthesis\\n"
        "• A Top-Down 'Past, Present, Future' Report\\n\\n"
        "⚡ *Quantum Score* calculated in < 5 seconds."
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not SecurityLayer.check_rate_limit(user_id, max_requests=5, window_seconds=60):
        await update.message.reply_text("⚠️ *Rate Limit Exceeded.*\\nPlease wait 60 seconds.", parse_mode="Markdown")
        return

    photo = update.message.photo[-1]
    file_info = await context.bot.get_file(photo.file_id)
    
    if not SecurityLayer.validate_image(file_info.file_size, file_info.file_path):
        await update.message.reply_text("⚠️ *Invalid File.* Please upload a standard image under 20MB.")
        return

    status_msg = await update.message.reply_text("👁️‍🗨️ *Quantum Vision Engaged. Scanning structure...*")

    try:
        user_tier = await get_user_tier(user_id)
        
        # CRITICAL FIX: Convert bytearray to strict bytes for Google Gemini API
        raw_data = await file_info.download_as_bytearray()
        image_bytes = bytes(raw_data)
        
        final_report = await quantum_engine.process_upload(image_bytes, user_tier)
        await status_msg.edit_text(final_report, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Quantum Analysis Failed: {e}")
        await status_msg.edit_text(f"⚠️ *Nexus Error:* `{str(e)}`", parse_mode="Markdown")
"""

with open("app/handlers/chart_handler.py", "w", encoding="utf-8") as f:
    f.write(code)

print("SUCCESS: chart_handler.py updated with strict bytes() conversion!")
