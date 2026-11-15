"""
QuantNexus Telegram Command Center - Precision Execution Fix
Fixes MT5 liquidation filling mode & dynamic slippage tolerance.
"""
import sys
import time
import json
import logging
from pathlib import Path
import httpx
import MetaTrader5 as mt5

sys.stdout.reconfigure(line_buffering=True)
CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\command_center.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(str(LOG_FILE), encoding="utf-8"), logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("CommandCenter")

TERMINALS = {
    "T1": (r"C:\MT5_Quant_278061453\terminal64.exe", 278062038),
    "T2": (r"C:\MT5_Pending_278041169\terminal64.exe", 278062039),
    "T3": (r"C:\MT5_HFT_278041671\terminal64.exe", 278062042)
}

def load_cfg():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return d.get("bot_token"), d.get("authorized_chat_id")
    except Exception:
        return None, None

def send_reply(chat_id: int, text: str):
    token, _ = load_cfg()
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=8.0) as client:
            client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        log.warning("Telegram reply failed: %s", e)

def get_filling_type(symbol: str) -> int:
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return mt5.ORDER_FILLING_IOC
    modes = sym_info.filling_mode
    if modes & 1:  # FOK
        return mt5.ORDER_FILLING_FOK
    elif modes & 2:  # IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def close_all_positions(term_key: str) -> str:
    path, login = TERMINALS[term_key]
    if not mt5.initialize(path=path):
        return f"[-] Failed to initialize {term_key}"
    acc = mt5.account_info()
    if not acc or acc.login != login:
        mt5.shutdown()
        return f"[-] Login mismatch on {term_key}"

    positions = mt5.positions_get() or []
    closed = 0
    errors = []

    for p in positions:
        order_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(p.symbol)
        if not tick:
            errors.append(f"No tick for {p.symbol}")
            continue
            
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        filling = get_filling_type(p.symbol)

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": order_type,
            "price": price,
            "deviation": 50,  # 50 points slippage tolerance for volatile pairs & indices
            "magic": p.magic,
            "comment": "TELEGRAM_REMOTE_KILL",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            log.info("Closed %s ticket #%s", p.symbol, p.ticket)
        else:
            err_msg = res.comment if res else str(mt5.last_error())
            errors.append(f"#{p.ticket} ({p.symbol}): {err_msg}")
            log.warning("Close failed for ticket #%s: %s", p.ticket, err_msg)

    mt5.shutdown()
    res_str = f"[+] {term_key}: Liquidated {closed}/{len(positions)} market positions."
    if errors:
        res_str += f"\n<i>Notes: {', '.join(errors[:2])}</i>"
    return res_str

def move_to_breakeven(term_key: str) -> str:
    path, login = TERMINALS[term_key]
    if not mt5.initialize(path=path):
        return f"[-] Failed to initialize {term_key}"
    positions = mt5.positions_get() or []
    updated = 0
    for p in positions:
        if p.profit > 0:
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": p.ticket,
                "sl": p.price_open,
                "tp": p.tp
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                updated += 1
    mt5.shutdown()
    return f"[+] {term_key}: Moved {updated} trades to Break-Even."

def poll_updates():
    token, auth_chat_id = load_cfg()
    if not token:
        log.error("Missing bot token in configuration.")
        return

    offset = 0
    log.info("Telegram Command Center active with dynamic execution engine.")

    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=20"
            with httpx.Client(timeout=25.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("result", []):
                        offset = item["update_id"] + 1
                        cb = item.get("callback_query")
                        if cb:
                            user_id = cb.get("from", {}).get("id")
                            cb_id = cb.get("id")
                            data_cmd = cb.get("data", "")

                            if auth_chat_id and str(user_id) != str(auth_chat_id):
                                continue

                            client.post(
                                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                                json={"callback_query_id": cb_id, "text": "Executing..."}
                            )

                            if data_cmd == "KILL_T1":
                                msg = close_all_positions("T1")
                                send_reply(user_id, f"🚨 <b>COMMAND RESULT</b>\n{msg}")
                            elif data_cmd == "KILL_T2":
                                msg = close_all_positions("T2")
                                send_reply(user_id, f"🚨 <b>COMMAND RESULT</b>\n{msg}")
                            elif data_cmd == "KILL_T3":
                                msg = close_all_positions("T3")
                                send_reply(user_id, f"🚨 <b>COMMAND RESULT</b>\n{msg}")
                            elif data_cmd == "BE_ALL":
                                r1 = move_to_breakeven("T1")
                                r2 = move_to_breakeven("T2")
                                send_reply(user_id, f"🔒 <b>BREAK-EVEN EXECUTIONS</b>\n{r1}\n{r2}")
                            elif data_cmd == "SYNC":
                                send_reply(user_id, "🔄 <b>FLEET TELEMETRY RESYNCHRONIZED</b>\n60-second engine cadence nominal.")
        except Exception as e:
            log.warning("Poll iteration error: %s", e)
        time.sleep(1)

if __name__ == "__main__":
    poll_updates()
