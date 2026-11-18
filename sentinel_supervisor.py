import os
import time
import json
import subprocess
import asyncio
from datetime import datetime
from telegram import Bot
import MetaTrader5 as mt5

TERMINAL_PATH = r'C:/MT5_Pending_278041169/terminal64.exe'
HEARTBEAT_FILE = 'daemon_heartbeat.json'
NEXUS_TOKEN = '8578781048:AAHCDrhqtH6gwcm1R3YZvNIu9zvAPM5Y5xU'
CHAT_ID = '5279761713'
STALE_THRESHOLD_SECONDS = 120

async def send_sentinel_alert(message: str):
    try:
        bot = Bot(token=NEXUS_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
    except Exception as e:
        print(f'[SENTINEL TELEGRAM ERROR] {e}')

def check_terminal_process():
    # Verify if terminal64.exe for Terminal 2 is running
    output = subprocess.check_output('tasklist /FI "IMAGENAME eq terminal64.exe"', shell=True).decode()
    return 'terminal64.exe' in output

def restart_terminal():
    print('[SENTINEL WARNING] Terminal 2 process unresponsive or missing. Restarting...')
    try:
        os.system(f'start "" "{TERMINAL_PATH}"')
        return True
    except Exception as e:
        print(f'[SENTINEL FATAL] Failed to restart terminal: {e}')
        return False

def sentinel_loop():
    print('🟢 *NEXUS SENTINEL SUPERVISOR ONLINE* — Monitoring Terminal 2 & Daemon Health...')
    while True:
        try:
            # 1. Check heartbeat file
            if os.path.exists(HEARTBEAT_FILE):
                with open(HEARTBEAT_FILE, 'r') as f:
                    data = json.load(f)
                    last_beat = data.get('timestamp', 0)
                    age = time.time() - last_beat
                    if age > STALE_THRESHOLD_SECONDS:
                        msg = f'🚨 *SENTINEL ALERT*: Daemon heartbeat stale by {age:.1f}s! Cycling terminal...'
                        asyncio.run(send_sentinel_alert(msg))
                        restart_terminal()
            
            # 2. Check process existence
            if not check_terminal_process():
                msg = '🚨 *SENTINEL ALERT*: Terminal 2 process (`terminal64.exe`) not found in process table. Restoring...'
                asyncio.run(send_sentinel_alert(msg))
                restart_terminal()
                
        except Exception as e:
            print(f'[SENTINEL ERROR] {e}')
            
        time.sleep(30)

if __name__ == '__main__':
    sentinel_loop()
