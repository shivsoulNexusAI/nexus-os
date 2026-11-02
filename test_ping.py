import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv(override=True)
token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
admin_id = int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", "5279761713").strip().strip('"').strip("'"))

print(f"Token length: {len(token)}")
print(f"Target Chat ID: {admin_id}")

async def send_test():
    bot = Bot(token=token)
    msg = await bot.send_message(
        chat_id=admin_id,
        text="⚡ [NEXUS TELEGRAM BOT READY]\nDirect link confirmed with chat ID: 5279761713."
    )
    print(f"[+] Successfully sent message! Telegram Message ID: {msg.message_id}")

asyncio.run(send_test())
