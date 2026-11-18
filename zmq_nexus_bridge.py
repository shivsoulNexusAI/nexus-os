import sys
import os
import zmq
import json
import asyncio
from telegram import Bot
import MetaTrader5 as mt5

TERMINAL_PATH = r'C:/MT5_Pending_278041169/terminal64.exe'
ZMQ_PUB_ENDPOINT = 'tcp://127.0.0.1:5555'
NEXUS_TOKEN = '8578781048:AAHCDrhqtH6gwcm1R3YZvNIu9zvAPM5Y5xU'
CHAT_ID = '5279761713'

async def send_telegram_alert(message: str):
    try:
        bot = Bot(token=NEXUS_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
    except Exception as e:
        print(f'[TELEGRAM ERROR] Failed to dispatch alert: {e}')

def run_event_bridge():
    print(f'[*] Initializing MetaTrader 5 for Terminal 2...')
    if not mt5.initialize(path=TERMINAL_PATH):
        print(f'[FATAL] MT5 Init failed: {mt5.last_error()}')
        return

    print(f'[*] Connecting to ZeroMQ Event Stream at {ZMQ_PUB_ENDPOINT}...')
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(ZMQ_PUB_ENDPOINT)
    socket.setsockopt_string(zmq.SUBSCRIBE, '')

    print('🟢 *NEXUS ZMQ EVENT-DRIVEN BRIDGE ONLINE* — Listening for MQL5 ticks & fills...')

    try:
        while True:
            message_bytes = socket.recv()
            event_data = json.loads(message_bytes.decode('utf-8'))
            
            event_type = event_data.get('type', 'UNKNOWN')
            symbol = event_data.get('symbol', 'N/A')
            ticket = event_data.get('ticket', 0)
            price = event_data.get('price', 0.0)
            
            print(f'[ZMQ EVENT] Type: {event_type} | Symbol: {symbol} | Ticket: {ticket} | Price: {price}')
            
            if event_type == 'ORDER_EXECUTION':
                acc = mt5.account_info()
                alert_msg = (
                    '⚡ *NEXUS ZERO-LATENCY EXECUTION*\n'
                    f'• Event: `{event_type}`\n'
                    f'• Symbol: `{symbol}`\n'
                    f'• Ticket: `{ticket}`\n'
                    f'• Fill Price: `{price}`\n'
                    f'• Current Equity: `${acc.equity:.2f}`'
                )
                asyncio.run(send_telegram_alert(alert_msg))
                
            elif event_type == 'REGIME_SHIFT':
                new_regime = event_data.get('regime', 'NEUTRAL')
                print(f'[ML REGIME] Structural shift detected for {symbol} -> {new_regime}')

    except KeyboardInterrupt:
        print('\n[*] Shutting down ZMQ bridge...')
    finally:
        socket.close()
        context.term()
        mt5.shutdown()

if __name__ == '__main__':
    run_event_bridge()
