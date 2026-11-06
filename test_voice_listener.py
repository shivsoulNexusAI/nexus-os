import os
import io
import asyncio
from dotenv import load_dotenv
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

load_dotenv(override=True)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", "5279761713").strip().strip('"').strip("'"))

recognizer = sr.Recognizer()

async def handle_voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_CHAT_ID:
        return

    voice = update.message.voice
    if not voice:
        return

    status_msg = await update.message.reply_text("🎙️ *Processing voice command...*", parse_mode="Markdown")

    try:
        # Download voice file from Telegram in memory
        voice_file = await context.bot.get_file(voice.file_id)
        ogg_bytes = io.BytesIO()
        await voice_file.download_to_memory(ogg_bytes)
        ogg_bytes.seek(0)

        # Convert OGG to WAV using pydub
        sound = AudioSegment.from_file(ogg_bytes, format="ogg")
        wav_io = io.BytesIO()
        sound.export(wav_io, format="wav")
        wav_io.seek(0)

        # Transcribe with SpeechRecognition
        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data).lower()

        print(f"[VOICE IN] Transcribed: '{text}'")

        # Routing voice intents
        if any(w in text for w in ["status", "profit", "balance", "equity", "position"]):
            reply = f"🗣️ *Heard:* \"{text}\"\n🎯 *Intent:* Account Status requested. Routing to `/status`..."
        elif any(w in text for w in ["scan", "market", "leaderboard", "pairs"]):
            reply = f"🗣️ *Heard:* \"{text}\"\n🎯 *Intent:* Universe Scan requested. Routing to `/scan`..."
        elif any(w in text for w in ["account", "switch", "terminal"]):
            reply = f"🗣️ *Heard:* \"{text}\"\n🎯 *Intent:* Accounts Switchboard requested. Routing to `/accounts`..."
        else:
            reply = f"🗣️ *Heard:* \"{text}\"\n❓ *Unrecognized Command.* Try saying 'status', 'scan', or 'accounts'."

        await status_msg.edit_text(reply, parse_mode="Markdown")

    except sr.UnknownValueError:
        await status_msg.edit_text("❌ *Could not understand audio.* Please speak clearly.", parse_mode="Markdown")
    except Exception as e:
        print(f"[!] Voice processing error: {e}")
        await status_msg.edit_text(f"⚠️ *Voice processing error:* `{e}`", parse_mode="Markdown")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_command))
    print("[ONLINE] Standalone Voice Command Listener Active. Send a voice note in Telegram!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
