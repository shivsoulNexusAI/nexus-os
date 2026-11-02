import os
import sys
import json
import time
import sqlite3
import logging
import argparse
import zmq
import MetaTrader5 as mt5

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SlaveWorker")

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
DB_PATH = os.path.join(BASE_DIR, "quant_metrics.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copier_mappings (
            master_ticket INTEGER PRIMARY KEY,
            slave_id TEXT NOT NULL,
            slave_ticket INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            master_lot REAL,
            slave_lot REAL,
            open_price REAL,
            status TEXT DEFAULT 'OPEN'
        )
    """)
    conn.commit()
    conn.close()

def get_best_filling_mode(symbol_info):
    mode = symbol_info.filling_mode
    # Bitmask check: SYMBOL_FILLING_FOK (1) -> ORDER_FILLING_FOK (0)
    if mode & 1:
        return mt5.ORDER_FILLING_FOK
    # Bitmask check: SYMBOL_FILLING_IOC (2) -> ORDER_FILLING_IOC (1)
    elif mode & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def execute_slave_order(trade_data, slave_id, risk_multiplier=1.0):
    symbol = trade_data["symbol"]
    order_type_str = trade_data["type"]
    master_lot = trade_data["volume"]
    
    acc_info = mt5.account_info()
    sym_info = mt5.symbol_info(symbol)
    if not acc_info or not sym_info:
        logger.error(f"[{slave_id}] Failed to fetch info for symbol {symbol}")
        return

    if not sym_info.visible:
        mt5.symbol_select(symbol, True)

    min_lot = sym_info.volume_min
    max_lot = sym_info.volume_max
    lot_step = sym_info.volume_step

    raw_lot = master_lot * risk_multiplier
    slave_lot = round(raw_lot / lot_step) * lot_step
    slave_lot = max(min_lot, min(max_lot, round(slave_lot, 2)))

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logger.error(f"[{slave_id}] Failed to get live tick for {symbol}")
        return

    is_buy = order_type_str == "BUY"
    price = tick.ask if is_buy else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL

    filling = get_best_filling_mode(sym_info)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": slave_lot,
        "type": order_type,
        "price": price,
        "sl": float(trade_data.get("sl", 0.0)),
        "tp": float(trade_data.get("tp", 0.0)),
        "deviation": 25,
        "magic": 999111,
        "comment": f"QN-Copy #{trade_data['ticket']}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    res = mt5.order_send(request)
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"✅ Slave [{slave_id}] Executed #{res.order} for Master #{trade_data['ticket']} ({slave_lot} lots)")
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT OR REPLACE INTO copier_mappings 
            (master_ticket, slave_id, slave_ticket, symbol, master_lot, slave_lot, open_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """, (trade_data["ticket"], slave_id, res.order, symbol, master_lot, slave_lot, price))
        conn.commit()
        conn.close()
    else:
        err_msg = res.comment if res else mt5.last_error()
        code = res.retcode if res else "None"
        logger.error(f"❌ Slave [{slave_id}] Order failed: {err_msg} (code: {code})")

def modify_slave_order(trade_data, slave_id):
    master_ticket = trade_data["master_ticket"]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT slave_ticket FROM copier_mappings WHERE master_ticket = ? AND slave_id = ?", (master_ticket, slave_id))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return

    slave_ticket = row[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": slave_ticket,
        "symbol": trade_data["symbol"],
        "sl": float(trade_data["sl"]),
        "tp": float(trade_data["tp"])
    }
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"🔧 Slave [{slave_id}] Position #{slave_ticket} modified: SL={trade_data['sl']}")

def close_slave_order(trade_data, slave_id):
    master_ticket = trade_data["master_ticket"]
    symbol = trade_data["symbol"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT slave_ticket, slave_lot FROM copier_mappings WHERE master_ticket = ? AND slave_id = ?", (master_ticket, slave_id))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return

    slave_ticket, slave_lot = row
    positions = mt5.positions_get(ticket=slave_ticket)
    if not positions:
        conn.close()
        return

    pos = positions[0]
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        conn.close()
        return

    is_buy = pos.type == mt5.POSITION_TYPE_BUY
    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    price = tick.bid if is_buy else tick.ask

    sym_info = mt5.symbol_info(symbol)
    filling = get_best_filling_mode(sym_info) if sym_info else mt5.ORDER_FILLING_RETURN

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": slave_ticket,
        "symbol": symbol,
        "volume": slave_lot,
        "type": close_type,
        "price": price,
        "deviation": 25,
        "type_filling": filling,
        "comment": f"Close QN #{master_ticket}"
    }

    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"🛑 Slave [{slave_id}] Position #{slave_ticket} closed.")
        cursor.execute("UPDATE copier_mappings SET status = 'CLOSED' WHERE master_ticket = ? AND slave_id = ?", (master_ticket, slave_id))
        conn.commit()
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Quant Nexus Slave Account Worker")
    parser.add_argument("--id", required=True, help="Unique Slave Identifier (e.g., Slave_01)")
    parser.add_argument("--path", required=False, default="", help="Path to terminal64.exe for isolated instances")
    parser.add_argument("--login", type=int, required=False, help="MT5 Login ID")
    parser.add_argument("--password", required=False, help="MT5 Password")
    parser.add_argument("--server", required=False, help="MT5 Server name")
    parser.add_argument("--multiplier", type=float, default=1.0, help="Lot size multiplier (default: 1.0)")
    args = parser.parse_args()

    init_db()

    init_kwargs = {}
    if args.path: init_kwargs["path"] = args.path
    if args.login: init_kwargs["login"] = args.login
    if args.password: init_kwargs["password"] = args.password
    if args.server: init_kwargs["server"] = args.server

    if not mt5.initialize(**init_kwargs):
        logger.error(f"Slave [{args.id}] MT5 init failed: {mt5.last_error()}")
        sys.exit(1)

    acc = mt5.account_info()
    logger.info(f"🛡️ Slave Worker [{args.id}] online. Linked Account: #{acc.login} | Server: {acc.server} | Balance: ${acc.balance:,.2f}")

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://127.0.0.1:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "TRADES")

    logger.info(f"⚡ Slave [{args.id}] listening to Master broadcasts...")

    try:
        while True:
            message = socket.recv_string()
            _, payload_json = message.split(" ", 1)
            event_obj = json.loads(payload_json)

            event = event_obj["event"]
            data = event_obj["data"]

            if event == "TRADE_OPEN":
                execute_slave_order(data, args.id, args.multiplier)
            elif event == "TRADE_MODIFY":
                modify_slave_order(data, args.id)
            elif event == "TRADE_CLOSE":
                close_slave_order(data, args.id)

    except KeyboardInterrupt:
        logger.info(f"Slave [{args.id}] shutting down...")
    finally:
        socket.close()
        context.term()
        mt5.shutdown()

if __name__ == "__main__":
    main()
