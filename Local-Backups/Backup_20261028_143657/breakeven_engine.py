import os
import time
import requests
import MetaTrader5 as mt5

LOGIN = 278017866
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"
TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# Load credentials from .env
env_path = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\.env"
env_vars = {}
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip('"').strip("'")

BOT_TOKEN = env_vars.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = env_vars.get("TELEGRAM_CHAT_ID")

def send_telegram(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

class BreakevenDefenseEngine:
    def __init__(self, r_multiple_trigger: float = 1.0, be_buffer_pips: float = 1.0):
        self.r_multiple_trigger = r_multiple_trigger
        self.be_buffer_pips = be_buffer_pips
        self.protected_tickets = set()

    def process_positions(self):
        positions = mt5.positions_get()
        if not positions:
            return

        for p in positions:
            if p.ticket in self.protected_tickets:
                continue

            info = mt5.symbol_info(p.symbol)
            if not info:
                continue

            pt = info.point
            digits = info.digits
            pip_size = pt * 10 if digits in [3, 5] else pt
            buffer_dist = self.be_buffer_pips * pip_size

            if p.sl == 0.0:
                continue

            is_buy = (p.type == mt5.ORDER_TYPE_BUY)
            initial_risk_dist = abs(p.price_open - p.sl)
            current_gain = (p.price_current - p.price_open) if is_buy else (p.price_open - p.price_current)

            # Trigger condition: profit >= 1.0R
            if current_gain >= (initial_risk_dist * self.r_multiple_trigger):
                new_sl = round(p.price_open + buffer_dist if is_buy else p.price_open - buffer_dist, digits)

                # Check if current SL already equals or surpasses breakeven
                if (is_buy and p.sl >= new_sl) or (not is_buy and p.sl <= new_sl):
                    self.protected_tickets.add(p.ticket)
                    continue

                # Broker stops_level safety check
                min_stop_distance = max(info.trade_stops_level, 5) * pt
                curr_price = p.price_current
                if is_buy and (curr_price - new_sl) < min_stop_distance:
                    continue  # Price too close to target SL, wait for safe buffer
                elif not is_buy and (new_sl - curr_price) < min_stop_distance:
                    continue

                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "sl": new_sl,
                    "tp": p.tp
                }
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    self.protected_tickets.add(p.ticket)
                    side_str = "BUY" if is_buy else "SELL"
                    msg = (
                        f"🔒 <b>[BREAKEVEN ARMED - RISK-FREE RUNNER]</b>\n"
                        f"• <b>Ticket</b>: #{p.ticket} ({p.symbol} {side_str})\n"
                        f"• <b>Volume</b>: <code>{p.volume:.2f}L</code>\n"
                        f"• <b>Open</b>  : <code>{p.price_open:.5f}</code>\n"
                        f"• <b>New SL</b>: <code>{new_sl:.5f}</code> (+{self.be_buffer_pips} pip lock)\n"
                        f"• <b>Float</b> : <b>+${p.profit:.2f} USD</b>\n"
                        f"• <b>Status</b>: Zero downside exposure locked."
                    )
                    send_telegram(msg)
                    print(f"[BREAKEVEN] Successfully locked Ticket #{p.ticket} on {p.symbol}")
                else:
                    err = res.comment if res else mt5.last_error()
                    print(f"[BREAKEVEN] Modification rejected for #{p.ticket}: {err}")

def main():
    if not mt5.initialize(path=TERMINAL_PATH) or not mt5.login(login=LOGIN, password=PASSWORD, server=SERVER):
        print(f"MT5 Login Failed: {mt5.last_error()}")
        return

    print("🟢 Breakeven Defense Engine Online. Polling active tickets...")
    engine = BreakevenDefenseEngine(r_multiple_trigger=1.0, be_buffer_pips=1.0)

    while True:
        try:
            engine.process_positions()
        except Exception as e:
            print(f"Breakeven Loop Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
