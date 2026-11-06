import sys
import json
import logging
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import MetaTrader5 as mt5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

CIRCUIT_BREAKER_FLOOR = 1015.80
MAX_FLEET_SLOTS = 4

def resolve_broker_symbol(target_sym):
    target = target_sym.upper()
    for s in [target, f"{target}m", f"{target}.a", f"{target}#"]:
        info = mt5.symbol_info(s)
        if info is not None:
            return s
    return target

def get_monte_carlo_state():
    acc = mt5.account_info()
    if not acc:
        return {"regime": "UNKNOWN", "scale": 0.5, "floor": CIRCUIT_BREAKER_FLOOR, "headroom": 0.0}
    
    headroom = acc.equity - CIRCUIT_BREAKER_FLOOR
    if acc.equity <= CIRCUIT_BREAKER_FLOOR:
        regime = "RED_LOCKOUT"
        scale = 0.0
    elif headroom < 50.0:
        regime = "YELLOW_DEFENSIVE"
        scale = 0.5
    else:
        regime = "GREEN_EXPANSION"
        scale = 1.0
        
    return {
        "regime": regime,
        "scale": scale,
        "floor": CIRCUIT_BREAKER_FLOOR,
        "headroom": round(headroom, 2)
    }

def get_session_realized_pnl_native():
    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    deals = mt5.history_deals_get(day_start, now) or []
    return round(sum(d.profit + d.swap + d.commission for d in deals), 2)

def calculate_setup_probability(dii, bar_delta, expansion_ratio, trend_delta, rates):
    prob = 50.0
    if abs(dii) >= 0.35:
        prob += 12.0
    elif abs(dii) >= 0.20:
        prob += 6.0
        
    if abs(bar_delta) > 100:
        prob += 8.0
        
    if expansion_ratio > 1.2:
        prob += 5.0
    elif expansion_ratio < 0.6:
        prob -= 8.0
        
    if rates is not None and len(rates) > 0:
        active_bar = rates[-1]
        candle_rng = float(active_bar['high'] - active_bar['low'])
        if candle_rng > 0:
            upper_wick = float(active_bar['high'] - max(active_bar['open'], active_bar['close']))
            lower_wick = float(min(active_bar['open'], active_bar['close']) - active_bar['low'])
            if lower_wick / candle_rng >= 0.45:
                prob += 6.0
            elif upper_wick / candle_rng >= 0.45:
                prob += 6.0

    return max(42.0, min(88.0, round(prob, 1)))

def analyze_single_symbol(sym_input, tf_str="M5"):
    actual_sym = resolve_broker_symbol(sym_input)
    mt5.symbol_select(actual_sym, True)
    tf_enum = TIMEFRAME_MAP.get(tf_str.upper(), mt5.TIMEFRAME_M5)

    tick = mt5.symbol_info_tick(actual_sym)
    bid = float(tick.bid) if tick else 0.0
    ask = float(tick.ask) if tick else 0.0

    rates = mt5.copy_rates_from_pos(actual_sym, tf_enum, 0, 25)
    if rates is None or len(rates) == 0:
        utc_to = datetime.now(timezone.utc)
        rates = mt5.copy_rates_from(actual_sym, tf_enum, utc_to, 25)

    if rates is not None and len(rates) > 0:
        active_bar = rates[-1]
        p_dir = 1 if active_bar['close'] >= active_bar['open'] else -1
        bar_delta = int(p_dir * int(active_bar['tick_volume']))
        tot_vol = sum(int(r['tick_volume']) for r in rates)
        tot_delta = sum((1 if r['close'] >= r['open'] else -1) * int(r['tick_volume']) for r in rates)
        dii = round(tot_delta / tot_vol, 2) if tot_vol > 0 else 0.0

        high_lows = [float(r['high'] - r['low']) for r in rates[:-1]]
        avg_range = sum(high_lows) / len(high_lows) if high_lows else 1.0
        curr_range = float(active_bar['high'] - active_bar['low'])
        expansion_ratio = round(curr_range / avg_range, 2) if avg_range > 0 else 1.0
        vpoc_price = round(float((active_bar['high'] + active_bar['low'] + active_bar['close']) / 3.0), 3)
    else:
        bar_delta = 0
        tot_delta = 0
        dii = 0.0
        expansion_ratio = 1.0
        vpoc_price = bid

    if bid == 0.0:
        sinfo = mt5.symbol_info(actual_sym)
        if sinfo:
            bid = float(sinfo.bid)
            ask = float(sinfo.ask)

    atr_status = "PERMITTED" if expansion_ratio <= 1.8 else "VETO_LOCKOUT"

    # Classify Order Flow Signal
    if dii <= -0.30 and bar_delta > 0:
        signal = "BULLISH_DELTA_DIVERGENCE"
        bias = "BUY"
    elif dii >= 0.30 and bar_delta < 0:
        signal = "BEARISH_ABSORPTION"
        bias = "SELL"
    elif dii > 0.20:
        signal = "TRENDING_BUY_AUCTION"
        bias = "BUY"
    elif dii < -0.20:
        signal = "TRENDING_SELL_AUCTION"
        bias = "SELL"
    else:
        signal = "BALANCED_AUCTION"
        bias = "NEUTRAL"

    prob = calculate_setup_probability(dii, bar_delta, expansion_ratio, tot_delta, rates)

    return {
        "symbol": sym_input.upper(),
        "broker_symbol": actual_sym,
        "timeframe": tf_str.upper(),
        "bid": bid,
        "ask": ask,
        "bar_delta": bar_delta,
        "cumulative_delta": tot_delta,
        "dii": dii,
        "expansion_ratio": expansion_ratio,
        "atr_status": atr_status,
        "signal": signal,
        "bias": bias,
        "setup_probability": prob,
        "vpoc_anchor": vpoc_price
    }

def calculate_parity_lot_size(symbol, scale_factor=0.5):
    try:
        from nexus_vol_parity_engine import calculate_risk_budgeted_volume
        vol = calculate_risk_budgeted_volume(symbol, scale_factor)
        if vol and vol >= 0.01:
            return round(vol, 2)
    except Exception as e:
        logging.warning(f"VolParity engine fallback: {e}")
    return 0.01

def get_fill_type(sym):
    sinfo = mt5.symbol_info(sym)
    if not sinfo:
        return mt5.ORDER_FILLING_IOC
    fm = sinfo.filling_mode
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    elif fm & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def handle_order_execution(sym, bias, volume=None):
    actual_sym = resolve_broker_symbol(sym)
    mt5.symbol_select(actual_sym, True)
    target_side = str(bias).upper()
    
    # --- INSTITUTIONAL NET DIRECTION & MAX-SLOT GATE ---
    active = mt5.positions_get() or []
    
    # Match symbols stripping broker suffixes if any
    for p in active:
        if p.symbol.rstrip('m').upper() == actual_sym.rstrip('m').upper():
            pos_side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
            if pos_side != target_side:
                logging.warning(f"[SlotGate] REJECTED {target_side} {actual_sym}: Opposing #{p.ticket} ({pos_side}) active.")
                return {"success": False, "error": f"Opposing direction active on {actual_sym}"}
            else:
                logging.warning(f"[SlotGate] REJECTED {target_side} {actual_sym}: Position already active. Scale-in locked.")
                return {"success": False, "error": f"Position already active on {actual_sym}"}

    if len(active) >= MAX_FLEET_SLOTS:
        logging.warning(f"[SlotGate] REJECTED {target_side} {actual_sym}: Max concurrent slots ({MAX_FLEET_SLOTS}) reached.")
        return {"success": False, "error": f"Max fleet capacity reached ({MAX_FLEET_SLOTS}/{MAX_FLEET_SLOTS})"}

    mc = get_monte_carlo_state()
    if mc["regime"] == "RED_LOCKOUT":
        return {"success": False, "error": "Circuit breaker RED_LOCKOUT. Trading halted."}

    # Volume determination
    if volume is None or float(volume) <= 0.0:
        vol = calculate_parity_lot_size(actual_sym, mc["scale"])
    else:
        vol = round(float(volume), 2)
        
    vol = max(0.01, vol)

    tick = mt5.symbol_info_tick(actual_sym)
    if not tick:
        return {"success": False, "error": f"Failed to get price tick for {actual_sym}"}

    order_type = mt5.ORDER_TYPE_BUY if target_side == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if target_side == "BUY" else tick.bid

    sym_u = actual_sym.upper()
    if "XAU" in sym_u or "GOLD" in sym_u:
        sl = round(price - 4.0 if target_side == "BUY" else price + 4.0, 2)
        tp = round(price + 9.5 if target_side == "BUY" else price - 9.5, 2)
    elif "BTC" in sym_u:
        sl = round(price - 350.0 if target_side == "BUY" else price + 350.0, 1)
        tp = round(price + 800.0 if target_side == "BUY" else price - 800.0, 1)
    else:
        sl = round(price - 0.0020 if target_side == "BUY" else price + 0.0020, 5)
        tp = round(price + 0.0050 if target_side == "BUY" else price - 0.0050, 5)

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": actual_sym,
        "volume": vol,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 50,
        "magic": 999101,
        "comment": "QuantNexus_C2_Parity",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_fill_type(actual_sym),
    }

    res = mt5.order_send(req)
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "retcode": res.retcode, "comment": res.comment}

    return {
        "success": True,
        "ticket": res.order,
        "symbol": actual_sym,
        "side": target_side,
        "volume": vol,
        "price": price,
        "sl": sl,
        "tp": tp
    }

class C2RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/telemetry":
            try:
                acc = mt5.account_info()
                acc_data = {
                    "login": acc.login,
                    "server": acc.server,
                    "equity": round(acc.equity, 2),
                    "balance": round(acc.balance, 2),
                    "currency": acc.currency
                } if acc else {}

                positions = []
                for p in (mt5.positions_get() or []):
                    positions.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "side": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                        "volume": p.volume,
                        "price_open": round(p.price_open, 5),
                        "price_current": round(p.price_current, 5),
                        "sl": round(p.sl, 5),
                        "tp": round(p.tp, 5),
                        "profit": round(p.profit, 2)
                    })

                watchlist = ["BTCUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY"]
                matrix = [analyze_single_symbol(s) for s in watchlist]

                payload = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "account": acc_data,
                    "monte_carlo": get_monte_carlo_state(),
                    "session_realized_pnl": get_session_realized_pnl_native(),
                    "active_fleet_positions": positions,
                    "market_matrix": matrix
                }
                self._send_json(200, payload)
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif url.path == "/api/execute":
            query = parse_qs(url.query)
            sym = query.get("symbol", [None])[0]
            bias = query.get("bias", ["BUY"])[0]
            vol = query.get("volume", [None])[0]

            if not sym:
                self._send_json(400, {"error": "Missing symbol parameter"})
                return

            res = handle_order_execution(sym, bias, vol)
            status = 200 if res.get("success") else 400
            self._send_json(status, res)
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def log_message(self, format, *args):
        pass

def run_server(port=8080):
    if not mt5.initialize():
        logging.error("[-] Failed to initialize MT5")
        sys.exit(1)

    logging.info(f"[+] MT5 Initialized. Login: {mt5.account_info().login}")
    server = HTTPServer(("0.0.0.0", port), C2RequestHandler)
    logging.info(f"[+] QuantNexus C2 Server online on port {port}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mt5.shutdown()
        logging.info("[*] C2 Server stopped.")

if __name__ == "__main__":
    run_server()
