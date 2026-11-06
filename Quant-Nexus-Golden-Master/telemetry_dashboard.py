from nexus_kelly_engine import kelly_engine
import os
import json
import time
import subprocess
import threading
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import MetaTrader5 as mt5
import numpy as np

app = FastAPI(title="Quant Nexus Telemetry & Radar C2")

LOGIN = 278017866
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"
CB_STATE_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\circuit_breaker_state.json"
CONFIG_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\runtime_config.json"

mt5_lock = threading.Lock()
radar_cache = {}
RADAR_CACHE_TTL = 15.0

cached_engines = {
    "watchdog": {"name": "Watchdog Supervisor", "running": False, "pid": None},
    "daemon": {"name": "Quantum Delta Daemon", "running": False, "pid": None},
    "deal_watcher": {"name": "Deal Resolution Watcher", "running": False, "pid": None},
    "breakeven": {"name": "Breakeven Engine", "running": False, "pid": None}
}

def poll_process_stack_background():
    global cached_engines
    while True:
        try:
            ps_cmd = 'Get-CimInstance Win32_Process | Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress'
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=8)
            if res.returncode == 0 and res.stdout.strip():
                raw = json.loads(res.stdout)
                procs = raw if isinstance(raw, list) else [raw]
                temp = {
                    "watchdog": {"name": "Watchdog Supervisor", "running": False, "pid": None},
                    "daemon": {"name": "Quantum Delta Daemon", "running": False, "pid": None},
                    "deal_watcher": {"name": "Deal Resolution Watcher", "running": False, "pid": None},
                    "breakeven": {"name": "Breakeven Engine", "running": False, "pid": None}
                }
                for p in procs:
                    cmd = p.get("CommandLine") or ""
                    pid = p.get("ProcessId")
                    if "watchdog_daemon.ps1" in cmd:
                        temp["watchdog"] = {"name": "Watchdog Supervisor", "running": True, "pid": pid}
                    elif "quantum_delta_daemon.py" in cmd:
                        temp["daemon"] = {"name": "Quantum Delta Daemon", "running": True, "pid": pid}
                    elif "deal_resolution_watcher.py" in cmd:
                        temp["deal_watcher"] = {"name": "Deal Resolution Watcher", "running": True, "pid": pid}
                    elif "breakeven_engine.py" in cmd:
                        temp["breakeven"] = {"name": "Breakeven Engine", "running": True, "pid": pid}
                cached_engines = temp
        except Exception:
            pass
        time.sleep(10)

threading.Thread(target=poll_process_stack_background, daemon=True).start()

def ensure_mt5():
    with mt5_lock:
        if not mt5.terminal_info():
            mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe")
            mt5.login(login=LOGIN, password=PASSWORD, server=SERVER)

def get_allowed_lot(sym: str) -> float:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                caps = cfg.get("max_allowed_lots", {})
                return float(caps.get(sym, cfg.get("default_max_lot", 0.05)))
        except Exception:
            pass
    return 0.02 if ("BTC" in sym or "XAU" in sym) else 0.05

@app.get("/api/telemetry")
def get_telemetry():
    hwm, floor, is_tripped = 0.0, 0.0, False
    cb_data = {}
    if os.path.exists(CB_STATE_PATH):
        try:
            with open(CB_STATE_PATH, "r", encoding="utf-8-sig") as f:
                cb_data = json.load(f)
                hwm = float(cb_data.get("high_water_mark", 0.0))
                floor = float(cb_data.get("current_floor", 0.0))
                is_tripped = bool(cb_data.get("is_tripped", False))
        except Exception:
            pass

    # Ensure MT5 is active before computing equity
    ensure_mt5()
    with mt5_lock:
        acc = mt5.account_info()
        live_equity = float(acc.equity) if acc else 0.0

    # Dynamic Ratchet: Trail HWM upward with equity peaks
    if live_equity > hwm and live_equity > 0.0:
        hwm = round(live_equity, 2)
        floor = round(hwm - 150.0, 2)
        cb_data["high_water_mark"] = hwm
        cb_data["current_floor"] = floor
        try:
            with open(CB_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(cb_data, f, indent=2)
        except Exception:
            pass

    account_data = {"balance": 0.0, "equity": 0.0, "margin_level": 0.0, "free_margin": 0.0}
    positions_data = []

    ensure_mt5()
    with mt5_lock:
        acc = mt5.account_info()
        if acc:
            account_data = {
                "balance": float(acc.balance),
                "equity": float(acc.equity),
                "margin_level": float(acc.margin_level),
                "free_margin": float(acc.margin_free)
            }
        positions = mt5.positions_get()

    if positions:
        for p in positions:
            is_buy = (p.type == mt5.ORDER_TYPE_BUY)
            risk = abs(p.price_open - p.sl) if p.sl > 0 else 0.0001
            gain = (p.price_current - p.price_open) if is_buy else (p.price_open - p.price_current)
            r_mult = gain / risk if risk > 0 else 0.0
            be = (is_buy and p.sl >= p.price_open) or (not is_buy and p.sl <= p.price_open and p.sl != 0.0)

            sym_info = mt5.symbol_info(p.symbol)
            d = sym_info.digits if sym_info else 4

            positions_data.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if is_buy else "SELL",
                "side": "BUY" if is_buy else "SELL",
                "volume": round(float(p.volume), 2),
                "entry_price": round(float(p.price_open), d),
                "open": round(float(p.price_open), d),
                "mark": round(float(p.price_current), d),
                "current_sl": round(float(p.sl), d),
                "sl": round(float(p.sl), d),
                "tp": round(float(p.tp), d),
                "floating_pnl": round(float(p.profit), 2),
                "profit": round(float(p.profit), 2),
                "r_mult": round(float(r_mult), 2),
                "be_locked": be
            })

    buffer_val = account_data["equity"] - floor if account_data["equity"] > 0 else 0.0

    return {
        "status": "ONLINE",
        "account": account_data,
        "circuit_breaker": {
            "hwm": float(hwm),
            "floor": float(floor),
            "buffer": float(buffer_val),
            "is_tripped": is_tripped
        },
        "cb_limit": 300.0,
        "realized_pnl": 0.0,
        "floating_pnl": round(float(account_data["equity"] - account_data["balance"]), 2),
        "engines": cached_engines,
        "positions": positions_data
    }

@app.get("/api/radar")
def get_radar(symbol: str = Query(..., description="Symbol"), tf: str = Query("M15", description="Timeframe")):
    cache_key = f"{symbol.upper()}_{tf.upper()}"
    now = time.time()

    if cache_key in radar_cache:
        val, expiry = radar_cache[cache_key]
        if now < expiry:
            return val

    ensure_mt5()
    tf_val = mt5.TIMEFRAME_M15 if tf.upper() == "M15" else mt5.TIMEFRAME_M5

    with mt5_lock:
        rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, 20)
        ticks = mt5.copy_ticks_from(symbol, 0, 80, mt5.COPY_TICKS_ALL)

    if rates is None or len(rates) < 10:
        res = {
            "symbol": symbol,
            "tf": tf,
            "setup_probability": 50.0,
            "bias": "NEUTRAL",
            "bar_delta": 0,
            "dii": 0.0,
            "atr_status": "VOLATILITY_LOCK"
        }
        radar_cache[cache_key] = (res, now + RADAR_CACHE_TTL)
        return res

    closes = np.array([r['close'] for r in rates])
    highs = np.array([r['high'] for r in rates])
    lows = np.array([r['low'] for r in rates])

    tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
    atr = float(np.mean(tr[-8:])) if len(tr) >= 8 else 0.001

    delta_price = closes[-1] - closes[-5]
    direction = "BUY" if delta_price > 0 else "SELL"

    change = abs(closes[-1] - closes[-8])
    volatility = np.sum(abs(closes[1:] - closes[:-1])[-8:])
    er = float(change / volatility) if volatility > 0 else 0.5

    spread_ratio = abs(delta_price) / atr if atr > 0 else 0.5
    prob = round(min(85.0, max(52.0, 68.0 + (spread_ratio * 4.5) + (er * 10.0))), 1)

    bar_delta = 0
    dii = 0.0
    if ticks is not None and len(ticks) > 10:
        bids = np.array([t['bid'] for t in ticks])
        diffs = np.diff(bids)
        up_ticks = int(np.sum(diffs > 0))
        down_ticks = int(np.sum(diffs < 0))
        bar_delta = up_ticks - down_ticks
        total_ticks = up_ticks + down_ticks
        dii = round(float(bar_delta / total_ticks), 2) if total_ticks > 0 else 0.0

    atr_status = "PERMITTED" if atr > 0 else "VOLATILITY_LOCK"

    res = {
        "symbol": symbol,
        "tf": tf,
        "setup_probability": prob,
        "bias": direction,
        "bar_delta": bar_delta,
        "dii": dii,
        "atr_status": atr_status
    }
    radar_cache[cache_key] = (res, now + RADAR_CACHE_TTL)
    return res

@app.get("/api/execute")
def execute_trade(symbol: str = Query(...), bias: str = Query(...)):
    ensure_mt5()
    side = bias.upper()
    order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
        # 1. Resolve live tick, price, and SL/TP bounds first
    tick = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    if not tick or not sym_info:
        return {"success": False, "error": f"Symbol info or tick unavailable for {symbol}"}

    digits = sym_info.digits
    point = sym_info.point
    is_buy = (bias.upper() == "BUY")
    price = tick.ask if is_buy else tick.bid

    # Derive SL/TP distances based on symbol baseline points (1.5 ATR / 3.0 ATR baseline)
    sl_distance = (250 * point) if "BTC" in symbol else (25 * point if "JPY" in symbol else 0.0020)
    tp_distance = sl_distance * 2.0

    sl = round(price - sl_distance if is_buy else price + sl_distance, digits)
    tp = round(price + tp_distance if is_buy else price - tp_distance, digits)

    # 2. Dynamic HP Half-Kelly Sizing
    hard_cap = get_allowed_lot(symbol)
    radar_prob = 75.0
    for tf_key in [f"{symbol.upper()}_M5", f"{symbol.upper()}_M15"]:
        if tf_key in radar_cache and len(radar_cache[tf_key]) > 0:
            radar_prob = radar_cache[tf_key][0].get("setup_probability", 75.0)
            break

    acc = mt5.account_info()
    current_equity = float(acc.equity) if acc else 1000.0

    volume = kelly_engine.compute_position_size(
        symbol=symbol,
        setup_probability=radar_prob,
        entry_price=price,
        sl_price=sl,
        tp_price=tp,
        account_equity=current_equity,
        hard_max_lot=hard_cap
    )

    with mt5_lock:
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {"success": False, "error": f"Cannot get tick for {symbol}"}

        price = tick.ask if side == "BUY" else tick.bid
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 14)
        if rates is not None and len(rates) >= 8:
            highs = np.array([r['high'] for r in rates])
            lows = np.array([r['low'] for r in rates])
            atr = float(np.mean(highs - lows))
        else:
            atr = 0.0010

        sl_dist = atr * 1.5
        tp_dist = atr * 3.0
        sl = price - sl_dist if side == "BUY" else price + sl_dist
        tp = price + tp_dist if side == "BUY" else price - tp_dist

        # Dynamic filling mode resolution for Exness
        sym_info = mt5.symbol_info(symbol)
        filling = mt5.ORDER_FILLING_FOK
        if sym_info:
            modes = sym_info.filling_mode
            if modes & 2: # SYMBOL_FILLING_IOC
                filling = mt5.ORDER_FILLING_IOC
            elif modes & 1: # SYMBOL_FILLING_FOK
                filling = mt5.ORDER_FILLING_FOK
            else:
                filling = mt5.ORDER_FILLING_RETURN

        digits = sym_info.digits if sym_info else 4

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": round(sl, digits),
            "tp": round(tp, digits),
            "deviation": 25,
            "magic": 999101,
            "comment": "Omega Apex Autonomous",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "error": f"MT5 retcode {result.retcode}: {result.comment}"}

    return {
        "success": True,
        "ticket": result.order,
        "volume": volume,
        "price": price,
        "sl": round(sl, 4),
        "tp": round(tp, 4)
    }

@app.get("/api/flatten")
def flatten_all():
    ensure_mt5()
    with mt5_lock:
        positions = mt5.positions_get()
        if not positions:
            return {"success": True, "closed": 0, "message": "Book already clean"}

        closed = 0
        for p in positions:
            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(p.symbol)
            if not tick:
                continue
            price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "price": price,
                "deviation": 25,
                "magic": 999101,
                "comment": "Matrix Flatten Triggered"
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1

    return {"success": True, "closed": closed}

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    return "<h1>Quant Nexus C2 Gateway Online</h1>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")






