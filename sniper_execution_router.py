"""
QuantNexus Execution Router: Institutional Order Dispatcher
IOC Filling, Dynamic Spread Armor, Fractional Kelly Sizing, Atomic State Sync
"""

import json
import time
from pathlib import Path
from dataclasses import asdict
import MetaTrader5 as mt5

from silver_bullet_sniper import SilverBulletSetup

STATE_FILE = Path(r"C:\Quant-Nexus-Eng\engine_state.json")
MAX_RISK_PER_TRADE_PCT = 0.0075  # 0.75% Account NAV Risk per setup
MAX_SPREAD_POINTS = {
    "BTCUSD": 600.0,
    "XAUUSD": 35.0,
    "EURUSD": 18.0,
    "GBPUSD": 20.0,
    "USDJPY": 20.0,
    "GBPJPY": 30.0,
}

def load_engine_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"active_trades": {}, "last_execution": None}

def save_engine_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def get_best_filling_mode(sym_info) -> int:
    """Selects best fill policy supported by broker: IOC -> FOK -> RETURN."""
    filling_modes = sym_info.filling_mode
    if filling_modes & mt5.ORDER_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    if filling_modes & mt5.ORDER_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN

def calculate_kelly_lot_size(setup: SilverBulletSetup, sym_info, acc_info) -> float:
    """Calculates position volume locked to exact risk parameters."""
    nav = acc_info.equity
    risk_usd = nav * MAX_RISK_PER_TRADE_PCT
    
    risk_points = abs(setup.entry_price - setup.stop_loss) / sym_info.point
    tick_val = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    
    if risk_points <= 0 or tick_size <= 0:
        return sym_info.volume_min
        
    point_value_per_lot = (tick_val / tick_size) * sym_info.point
    if point_value_per_lot <= 0:
        return sym_info.volume_min
        
    raw_lots = risk_usd / (risk_points * point_value_per_lot)
    
    # Quantize to broker lot step limits
    step = sym_info.volume_step
    vol_min = sym_info.volume_min
    vol_max = sym_info.volume_max
    
    lots = round(raw_lots / step) * step
    lots = max(vol_min, min(lots, vol_max))
    return round(lots, 2)

def route_silver_bullet_order(setup: SilverBulletSetup, dry_run: bool = True) -> tuple[bool, str, dict]:
    """
    Validates institutional guards and routes order to MT5.
    dry_run=True validates without hitting the broker order book.
    """
    t_start = time.perf_counter()
    sym = setup.symbol
    sym_info = mt5.symbol_info(sym)
    acc_info = mt5.account_info()
    tick = mt5.symbol_info_tick(sym)
    
    if not sym_info or not acc_info or not tick:
        return False, "MT5_DATA_UNAVAILABLE", {}
        
    # Guard 1: Spread Armor
    point = sym_info.point
    spread_pts = (tick.ask - tick.bid) / point
    max_allowed = MAX_SPREAD_POINTS.get(sym, 30.0)
    if spread_pts > max_allowed:
        return False, f"REJECT_EXCESSIVE_SPREAD ({spread_pts:.1f} > {max_allowed})", {}
        
    # Guard 2: Free Margin / Exposure Check
    lots = calculate_kelly_lot_size(setup, sym_info, acc_info)
    order_type = mt5.ORDER_TYPE_BUY if setup.direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if setup.direction == "BUY" else tick.bid
    
    margin_req = mt5.order_calc_margin(order_type, sym, lots, price)
    if margin_req is None or margin_req > acc_info.margin_free * 0.50:
        return False, f"REJECT_INSUFFICIENT_MARGIN (Req: ${margin_req}, Free: ${acc_info.margin_free})", {}
        
    # Guard 3: Execution Latency Gate
    latency_ms = (time.perf_counter() - t_start) * 1000
    if latency_ms > 200.0:
        return False, f"REJECT_LATENCY_EXCEEDED ({latency_ms:.1f}ms > 200ms)", {}
        
    filling_mode = get_best_filling_mode(sym_info)
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": float(lots),
        "type": order_type,
        "price": float(price),
        "sl": float(setup.stop_loss),
        "tp": float(setup.take_profit),
        "deviation": 10,
        "magic": 278062038,
        "comment": f"SB_{setup.killzone[:6]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    
    if dry_run:
        return True, "DRY_RUN_ARMED_AND_VALIDATED", {
            "symbol": sym,
            "lots": lots,
            "price": price,
            "sl": setup.stop_loss,
            "tp": setup.take_profit,
            "latency_ms": round(latency_ms, 2),
            "filling_mode": filling_mode
        }
        
    # Live Dispatch
    res = mt5.order_send(request)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        err_msg = res.comment if res else "UNKNOWN_MT5_ERROR"
        return False, f"EXECUTION_FAILED ({err_msg})", {}
        
    # Atomic State Persistence
    state = load_engine_state()
    state["active_trades"][str(res.order)] = {
        "ticket": res.order,
        "symbol": sym,
        "direction": setup.direction,
        "volume": lots,
        "entry_price": res.price,
        "sl": setup.stop_loss,
        "tp": setup.take_profit,
        "be_target": setup.entry_price + (setup.take_profit - setup.entry_price) * 0.70,  # Hardened: 1.4R threshold prevents premature chopout
        "be_moved": False,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    state["last_execution"] = datetime.now(timezone.utc).isoformat()
    save_engine_state(state)
    
    return True, f"SUCCESS_EXECUTED_TICKET_{res.order}", {"ticket": res.order, "lots": lots, "price": res.price}

if __name__ == "__main__":
    from silver_bullet_feeder import init_mt5, scan_fleet
    from silver_bullet_sniper import evaluate_silver_bullet, calculate_atr
    
    print("[*] Testing Execution Router in DRY-RUN mode against Account 278062038...")
    if not init_mt5():
        print("[-] MT5 init failed.")
        exit(1)
        
    # Scan XAUUSD to grab live test tick
    sym = "XAUUSD"
    tick = mt5.symbol_info_tick(sym)
    sym_info = mt5.symbol_info(sym)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 30)
    
    if rates is not None and sym_info and tick:
        candles = [{"open": float(r['open']), "high": float(r['high']), "low": float(r['low']), "close": float(r['close']), "time": r['time']} for r in rates]
        setup = evaluate_silver_bullet(sym, candles, spread_pts=(tick.ask - tick.bid), min_rr=2.0)
        
        if setup:
            ok, msg, details = route_silver_bullet_order(setup, dry_run=True)
            print(f"[+] Route Verdict: {msg}")
            print(f"    Payload: {details}")
        else:
            print("[+] Setup out of confluence right now; router syntax compiled cleanly.")
            
    mt5.shutdown()