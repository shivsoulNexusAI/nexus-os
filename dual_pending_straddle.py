import time
import json
import logging
import urllib.request
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CONFIG_PATH = "C:\\Quant-Nexus-Prod\\core\\telegram_config.json"
MAX_SLOTS = 4
POLL_INTERVAL_SEC = 15

UNIVERSE_CONFIG = {
    "BTCUSD": {"tf": mt5.TIMEFRAME_M15, "lookback": 16, "spread_pad_pts": 500, "kc_mult": 1.5, "lot": 0.01},
    "XAUUSD": {"tf": mt5.TIMEFRAME_M15, "lookback": 12, "spread_pad_pts": 80,  "kc_mult": 1.5, "lot": 0.01},
    "EURUSD": {"tf": mt5.TIMEFRAME_M15, "lookback": 20, "spread_pad_pts": 15,  "kc_mult": 1.5, "lot": 0.01},
    "GBPUSD": {"tf": mt5.TIMEFRAME_M15, "lookback": 16, "spread_pad_pts": 20,  "kc_mult": 1.5, "lot": 0.01},
    "USDJPY": {"tf": mt5.TIMEFRAME_M15, "lookback": 16, "spread_pad_pts": 20,  "kc_mult": 1.5, "lot": 0.01},
    "GBPJPY": {"tf": mt5.TIMEFRAME_M15, "lookback": 12, "spread_pad_pts": 35,  "kc_mult": 1.5, "lot": 0.01},
}

# In-memory tracking of active brackets: {group_id: {"symbol": sym, "buy_ticket": int, "sell_ticket": int}}
ACTIVE_OCO_PAIRS = {}

def load_tg_cfg():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def send_oco_alert(html_text: str):
    cfg = load_tg_cfg()
    token = cfg.get("bot_token")
    chat_id = cfg.get("chat_id")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception as e:
        logging.warning(f"Telegram OCO alert failed: {e}")

def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def evaluate_squeeze(sym, cfg):
    rates = mt5.copy_rates_from_pos(sym, cfg["tf"], 0, 120)
    if rates is None or len(rates) < 120:
        return None
    df = pd.DataFrame(rates)
    close = df["close"]
    
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = sma20 + (2.0 * std20)
    bb_lower = sma20 - (2.0 * std20)

    atr20 = calculate_atr(df, 20)
    kc_upper = sma20 + (cfg["kc_mult"] * atr20)
    kc_lower = sma20 - (cfg["kc_mult"] * atr20)

    is_squeeze = (bb_upper.iloc[-1] < kc_upper.iloc[-1]) and (bb_lower.iloc[-1] > kc_lower.iloc[-1])
    atr14 = calculate_atr(df, 14).iloc[-1]
    atr100 = calculate_atr(df, 100).iloc[-1]
    atr_ratio = atr14 / atr100 if atr100 > 0 else 1.0

    lookback = cfg["lookback"]
    box_high = df["high"].iloc[-lookback:].max()
    box_low = df["low"].iloc[-lookback:].min()

    info = mt5.symbol_info(sym)
    point = info.point if info else 0.00001
    spread_pts = info.spread if info else 10
    total_offset = (spread_pts + cfg["spread_pad_pts"]) * point
    digits = info.digits if info else 5

    buy_stop = round(box_high + total_offset, digits)
    sell_stop = round(box_low - total_offset, digits)
    box_mid = round((box_high + box_low) / 2.0, digits)

    # 1.5R default target expansion
    range_pts = (box_high - box_low)
    buy_tp = round(buy_stop + (range_pts * 1.5), digits)
    sell_tp = round(sell_stop - (range_pts * 1.5), digits)

    return {
        "symbol": sym,
        "is_squeeze": bool(is_squeeze),
        "atr_ratio": float(atr_ratio),
        "buy_stop": buy_stop,
        "sell_stop": sell_stop,
        "sl_mid": box_mid,
        "buy_tp": buy_tp,
        "sell_tp": sell_tp,
        "lot": cfg["lot"]
    }

def place_pending_bracket(sq):
    sym = sq["symbol"]
    group_id = f"OCO_{int(time.time())}_{sym}"
    
    # 1. Place Buy Stop
    buy_req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": sym,
        "volume": sq["lot"],
        "type": mt5.ORDER_TYPE_BUY_STOP,
        "price": sq["buy_stop"],
        "sl": sq["sl_mid"],
        "tp": sq["buy_tp"],
        "deviation": 20,
        "magic": 888111,
        "comment": f"{group_id}_BUY",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res_buy = mt5.order_send(buy_req)
    if not res_buy or res_buy.retcode != mt5.TRADE_RETCODE_DONE:
        logging.warning(f"Buy Stop placement failed for {sym}: {getattr(res_buy, 'comment', 'error')}")
        return False

    buy_ticket = res_buy.order

    # 2. Place Sell Stop
    sell_req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": sym,
        "volume": sq["lot"],
        "type": mt5.ORDER_TYPE_SELL_STOP,
        "price": sq["sell_stop"],
        "sl": sq["sl_mid"],
        "tp": sq["sell_tp"],
        "deviation": 20,
        "magic": 888111,
        "comment": f"{group_id}_SELL",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res_sell = mt5.order_send(sell_req)
    if not res_sell or res_sell.retcode != mt5.TRADE_RETCODE_DONE:
        logging.warning(f"Sell Stop placement failed for {sym}. Canceling paired Buy Stop #{buy_ticket}...")
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": buy_ticket})
        return False

    sell_ticket = res_sell.order

    ACTIVE_OCO_PAIRS[group_id] = {
        "symbol": sym,
        "buy_ticket": buy_ticket,
        "sell_ticket": sell_ticket,
        "buy_price": sq["buy_stop"],
        "sell_price": sq["sell_stop"],
        "sl": sq["sl_mid"]
    }

    logging.info(f"[+] DUAL BRACKET ARMED: {sym} | BuyStop #{buy_ticket} @ {sq['buy_stop']} | SellStop #{sell_ticket} @ {sq['sell_stop']}")
    
    # Send Telemetry Alert
    card = (
        "⚔️ <b>QUANTNEXUS: DUAL PENDING OCO ARMED</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"• <b>Instrument:</b>  <code>{sym}</code> (Squeeze Expansion)\n"
        f"• <b>Buy Stop:</b>    <code>{sq['buy_stop']}</code> (Ticket #{buy_ticket})\n"
        f"• <b>Sell Stop:</b>   <code>{sq['sell_stop']}</code> (Ticket #{sell_ticket})\n"
        f"• <b>Risk SL (Mid):</b> <code>{sq['sl_mid']}</code>\n"
        f"• <b>Strategy:</b>    <code>Atomic 1-Cancels-Other</code>\n"
        f"• <b>Timestamp:</b>   <code>{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</code>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        "<i>Vol-Coil Compression Trigger Ready</i>"
    )
    send_oco_alert(card)
    return True

def monitor_atomic_oco_resolution():
    """
    Sub-second order resolution monitor:
    Checks if one pending order filled into an open position.
    If so, immediately cancels the opposite pending order.
    """
    if not ACTIVE_OCO_PAIRS:
        return

    orders = mt5.orders_get()
    positions = mt5.positions_get()
    
    active_order_tickets = {o.ticket for o in orders} if orders else set()
    active_position_tickets = {p.ticket for p in positions} if positions else set()

    resolved_groups = []

    for gid, data in list(ACTIVE_OCO_PAIRS.items()):
        b_tick = data["buy_ticket"]
        s_tick = data["sell_ticket"]
        sym = data["symbol"]

        buy_filled = (b_tick not in active_order_tickets) and (b_tick in active_position_tickets)
        sell_filled = (s_tick not in active_order_tickets) and (s_tick in active_position_tickets)

        if buy_filled:
            logging.info(f"[OCO-FILL] Buy Stop #{b_tick} filled! Canceling Sell Stop #{s_tick}...")
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": s_tick})
            resolved_groups.append(gid)
            send_oco_alert(
                f"🎯 <b>OCO TRIGGERED: BUY STOP FILLED</b>\n"
                f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
                f"• Pair: <b>{sym}</b>\n"
                f"• Execution: <code>#{b_tick} (LONG EXPANSION)</code>\n"
                f"• Atomic OCO: <code>#{s_tick} CANCELLED</code>\n"
                f"• Status: Active Runner Engaged"
            )

        elif sell_filled:
            logging.info(f"[OCO-FILL] Sell Stop #{s_tick} filled! Canceling Buy Stop #{b_tick}...")
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": b_tick})
            resolved_groups.append(gid)
            send_oco_alert(
                f"🎯 <b>OCO TRIGGERED: SELL STOP FILLED</b>\n"
                f"<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
                f"• Pair: <b>{sym}</b>\n"
                f"• Execution: <code>#{s_tick} (SHORT EXPANSION)</code>\n"
                f"• Atomic OCO: <code>#{b_tick} CANCELLED</code>\n"
                f"• Status: Active Runner Engaged"
            )
            
        elif (b_tick not in active_order_tickets) and (s_tick not in active_order_tickets):
            # Both orders removed or expired
            resolved_groups.append(gid)

    for gid in resolved_groups:
        del ACTIVE_OCO_PAIRS[gid]

def run_oco_daemon():
    if not mt5.initialize():
        logging.error("MT5 link failed in OCO Daemon.")
        return

    logging.info("[*] Dual Pending Stop OCO Engine initialized and armed...")

    while True:
        try:
            # 1. Fast sub-cycle monitor for atomic OCO pruning
            for _ in range(POLL_INTERVAL_SEC):
                monitor_atomic_oco_resolution()
                time.sleep(1)

            # 2. Portfolio and slot gating
            positions = mt5.positions_get()
            pos_count = len(positions) if positions else 0
            if pos_count >= MAX_SLOTS:
                continue

            open_symbols = {p.symbol for p in positions} if positions else set()
            pending_orders = mt5.orders_get()
            if pending_orders:
                for o in pending_orders:
                    open_symbols.add(o.symbol)

            # 3. Scan universe for qualifying compression setups
            for sym, cfg in UNIVERSE_CONFIG.items():
                if sym in open_symbols:
                    continue
                
                sq = evaluate_squeeze(sym, cfg)
                if not sq:
                    continue

                # Qualify on active squeeze or deep compression
                if sq["is_squeeze"] or sq["atr_ratio"] <= 0.70:
                    logging.info(f"[COIL DETECTED] {sym} Squeeze: {sq['is_squeeze']} | ATR Ratio: {sq['atr_ratio']:.2f} -> Arming Brackets")
                    place_pending_bracket(sq)
                    break  # Arm one qualified pair per cycle

        except Exception as e:
            logging.error(f"OCO Daemon Cycle Error: {e}")
            time.sleep(2)

if __name__ == "__main__":
    run_oco_daemon()