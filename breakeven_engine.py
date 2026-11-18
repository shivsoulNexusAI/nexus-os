# -*- coding: utf-8 -*-
"""
QUANT-NEXUS RAPID PROFIT PROTECTION & DYNAMIC TRAILING ENGINE (V2.1)
Covers Silo 1 (#278062038), Silo 2 (#278062039), and Silo 3 (#278062042)
with Non-Blocking Real-Time Telegram Telemetry
"""
import os
import sys
import json
import time
import math
import logging
import threading
from pathlib import Path
import httpx
import MetaTrader5 as mt5

ROOT_DIR = Path(r"C:\Quant-Nexus-Eng")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TG_TOKEN = ""
TG_CHAT_ID = ""
for cfg_mod in ("telegram_nexus_config", "telegram_config", "nexus_tg_config"):
    try:
        m = __import__(cfg_mod)
        TG_TOKEN = getattr(m, "BOT_TOKEN", getattr(m, "TELEGRAM_BOT_TOKEN", getattr(m, "TOKEN", TG_TOKEN)))
        TG_CHAT_ID = str(getattr(m, "CHAT_ID", getattr(m, "TELEGRAM_CHAT_ID", getattr(m, "CHANNEL_ID", TG_CHAT_ID))))
        if TG_TOKEN and TG_CHAT_ID:
            break
    except Exception:
        pass

try:
    from telegram_notifier_v43 import send_v43_alert as _v43_send
except Exception:
    _v43_send = None

def send_be_tg(html_msg: str):
    """Non-blocking Telegram dispatch so network latency never stalls the 3s BE audit loop."""
    def _worker():
        try:
            if _v43_send is not None:
                _v43_send(html_msg)
                return
            if TG_TOKEN and TG_CHAT_ID:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                with httpx.Client(timeout=6.0) as client:
                    client.post(url, json={
                        "chat_id": TG_CHAT_ID,
                        "text": html_msg,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    })
        except Exception as exc:
            log.warning("[BE-TG] Dispatch warning: %s", exc)

    threading.Thread(target=_worker, daemon=True).start()

LOG_FILE = ROOT_DIR / "breakeven_engine.log"
STATE_PATH = ROOT_DIR / "breakeven_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("BreakevenEngine")

SILOS = [
    {
        "name": "Silo 1 (Apex Satellite)",
        "login": 278062038,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe",
        "portable": False
    },
    {
        "name": "Silo 2 (Pending FX)",
        "login": 278062039,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_Pending_278041169\terminal64.exe",
        "portable": False
    },
    {
        "name": "Silo 3 (HFT Gold)",
        "login": 278062042,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_HFT_278041671\terminal64.exe",
        "portable": False
    }
]

SPREAD_PAD_POINTS = {
    "EURUSD": 12,
    "GBPUSD": 15,
    "USDJPY": 15,
    "AUDUSD": 15,
    "USDCAD": 15,
    "GBPJPY": 25,
    "XAUUSD": 60,
    "BTCUSD": 300,
    "US30": 30
}

scaled_tickets = set()
initial_risk_cache = {}
last_trail_tg_ts = {}  # ticket -> epoch float to rate-limit Tier 3 trail alerts

def load_state():
    global scaled_tickets, initial_risk_cache
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                scaled_tickets = set(data.get("scaled_tickets", []))
                initial_risk_cache = {str(k): float(v) for k, v in data.get("initial_risk_cache", {}).items()}
        except Exception as e:
            log.warning("Error loading BE state: %s", e)

def save_state():
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "scaled_tickets": list(scaled_tickets),
                "initial_risk_cache": initial_risk_cache
            }, f, indent=2)
    except Exception as e:
        log.warning("Error saving BE state: %s", e)

def get_supported_filling(symbol):
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return mt5.ORDER_FILLING_IOC
    modes = sym_info.filling_mode
    if modes & 1:
        return mt5.ORDER_FILLING_FOK
    elif modes & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def audit_silo(silo):
    path = silo["path"]
    login = silo["login"]
    portable = silo["portable"]

    if not mt5.initialize(path=path, portable=portable):
        log.warning("MT5 Init failed for %s: %s", silo["name"], mt5.last_error())
        return

    acc = mt5.account_info()
    if not acc or acc.login != login:
        if not mt5.login(login=login, password=silo["password"], server=silo["server"]):
            log.warning("Login failed for %s (#%s): %s", silo["name"], login, mt5.last_error())
            mt5.shutdown()
            return

    positions = mt5.positions_get() or []
    if not positions:
        mt5.shutdown()
        return

    active_tickets = {p.ticket for p in positions}
    active_ticket_strs = {str(p.ticket) for p in positions}

    dirty = False
    dead_tickets = scaled_tickets - active_tickets
    if dead_tickets:
        scaled_tickets.difference_update(dead_tickets)
        dirty = True

    for stale_k in list(initial_risk_cache.keys()):
        if stale_k not in active_ticket_strs:
            initial_risk_cache.pop(stale_k, None)
            dirty = True

    for stale_t in list(last_trail_tg_ts.keys()):
        if stale_t not in active_tickets:
            last_trail_tg_ts.pop(stale_t, None)

    for p in positions:
        ticket = p.ticket
        t_key = str(ticket)
        sym = p.symbol
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        side_str = "BUY" if is_buy else "SELL"
        open_price = float(p.price_open)
        mark = float(p.price_current)
        sl = float(p.sl)
        volume = float(p.volume)

        sym_info = mt5.symbol_info(sym)
        if not sym_info:
            continue

        digits = sym_info.digits
        point = sym_info.point
        pad_pts = SPREAD_PAD_POINTS.get(sym.rstrip("m"), 20)
        spread_pad = pad_pts * point

        if t_key not in initial_risk_cache:
            if sl > 0 and abs(open_price - sl) > spread_pad:
                initial_risk_cache[t_key] = abs(open_price - sl)
            else:
                initial_risk_cache[t_key] = 200 * point
            dirty = True

        initial_risk = initial_risk_cache[t_key]
        gain = (mark - open_price) if is_buy else (open_price - mark)
        r_mult = gain / initial_risk if initial_risk > 0 else 0.0

        # === TIER 1: BREAKEVEN LOCK AT +0.65R (Locks +0.20R cushion) ===
        if r_mult >= 0.65:
            be_cushion = max(spread_pad, 0.18 * initial_risk)
            target_be_sl = round(open_price + be_cushion if is_buy else open_price - be_cushion, digits)
            eps = 0.5 * point
            needs_be_lock = (is_buy and ((target_be_sl - sl) > eps or sl == 0.0)) or (
                not is_buy and ((sl - target_be_sl) > eps or sl == 0.0)
            )

            if needs_be_lock:
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "symbol": sym,
                    "sl": target_be_sl,
                    "tp": p.tp
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log.info("[TIER 1 +0.65R BE-LOCK] %s #%s (%s) at +%.2fR -> SL locked at %s", silo["name"], ticket, sym, r_mult, target_be_sl)
                    send_be_tg(
                        f"🛡️ <b>[NEXUS BE V2.1 // +0.65R BREAKEVEN LOCK]</b>\n"
                        f"• Silo: <b>{silo['name']}</b> (<code>#{login}</code>)\n"
                        f"• Asset: <b>{sym}</b> ({side_str} {volume}L) | Ticket: <code>#{ticket}</code>\n"
                        f"• Expansion: <b>+{r_mult:.2f}R</b> (Entry: <code>{open_price}</code>)\n"
                        f"• Protected SL: <b><code>{target_be_sl}</code></b> (+0.20R cushion locked)"
                    )
                    sl = target_be_sl

        # === TIER 2: 50% PARTIAL HARVEST AT +1.15R (Positions >= 0.02 lots) ===
        if r_mult >= 1.15 and ticket not in scaled_tickets:
            step = sym_info.volume_step
            min_lot = sym_info.volume_min
            half_vol = round(math.floor((volume / 2.0) / step) * step, 2)

            if half_vol >= min_lot and (volume - half_vol) >= min_lot:
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                close_price = sym_info.bid if is_buy else sym_info.ask
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": ticket,
                    "symbol": sym,
                    "volume": half_vol,
                    "type": close_type,
                    "price": close_price,
                    "deviation": 25,
                    "magic": p.magic,
                    "comment": "Nexus_Harvest_1.6R",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": get_supported_filling(sym)
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    scaled_tickets.add(ticket)
                    save_state()
                    dirty = True
                    rem_vol = round(volume - half_vol, 2)
                    log.info("[TIER 2 HARVEST] %s #%s (%s) banked 50%% (%.2fL) at +%.2fR", silo["name"], ticket, sym, half_vol, r_mult)
                    send_be_tg(
                        f"💰 <b>[NEXUS BE V2.1 // +1.15R PARTIAL HARVEST]</b>\n"
                        f"• Silo: <b>{silo['name']}</b> (<code>#{login}</code>)\n"
                        f"• Asset: <b>{sym}</b> ({side_str}) | Ticket: <code>#{ticket}</code>\n"
                        f"• Banked 50%: <b>{half_vol}L</b> @ <code>{close_price}</code> (<b>+{r_mult:.2f}R</b>)\n"
                        f"• Active Runner: <b>{rem_vol}L</b> riding with SL <code>{sl}</code>"
                    )

        # === TIER 3: M1 MICRO-SWING TRAILING STOP (Activates >= +1.50R) ===
        if r_mult >= 1.05:
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 1, 2)
            if rates is not None and len(rates) >= 2:
                proposed_sl = None
                if is_buy:
                    lowest_low = min(rates[0]["low"], rates[1]["low"])
                    cand = round(lowest_low - spread_pad, digits)
                    if cand > sl and cand > (open_price + spread_pad):
                        proposed_sl = cand
                else:
                    highest_high = max(rates[0]["high"], rates[1]["high"])
                    cand = round(highest_high + spread_pad, digits)
                    if (sl == 0.0 or cand < sl) and cand < (open_price - spread_pad):
                        proposed_sl = cand

                if proposed_sl is not None:
                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": ticket,
                        "symbol": sym,
                        "sl": proposed_sl,
                        "tp": p.tp
                    })
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        log.info("[TIER 3 TRAIL] %s #%s (%s %s) SL trailed to %s", silo["name"], ticket, sym, side_str, proposed_sl)
                        now_ts = time.time()
                        if (now_ts - last_trail_tg_ts.get(ticket, 0.0)) >= 60.0:
                            last_trail_tg_ts[ticket] = now_ts
                            send_be_tg(
                                f"📈 <b>[NEXUS BE V2.1 // +1.50R M1 MICRO-SWING TRAIL]</b>\n"
                                f"• Silo: <b>{silo['name']}</b> (<code>#{login}</code>)\n"
                                f"• Asset: <b>{sym}</b> ({side_str}) | Ticket: <code>#{ticket}</code>\n"
                                f"• Current Gain: <b>+{r_mult:.2f}R</b>\n"
                                f"• Ratcheted SL: <code>{sl}</code> → <b><code>{proposed_sl}</code></b>"
                            )

    if dirty:
        save_state()
    mt5.shutdown()

def main():
    log.info("Starting Calibrated V2.1 Breakeven & Trailing Engine + Telegram Telemetry across Silos 1, 2, 3...")
    load_state()
    while True:
        try:
            for silo in SILOS:
                audit_silo(silo)
        except Exception as e:
            log.error("Breakeven cycle exception: %s", e)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
