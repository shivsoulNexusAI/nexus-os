import math

# =====================================================================
# MATHEMATICAL HALF-KELLY DYNAMIC SIZING ENGINE
# =====================================================================
def calculate_half_kelly_lot(symbol: str, entry_price: float, sl_price: float,
                             win_rate: float = 0.62, payoff_ratio: float = 1.50,
                             max_risk_pct: float = 0.015) -> float:
    """
    Computes lot volume via Half-Kelly Criterion adjusted for broker ticks,
    spread points, and institutional margin bounds.
    """
    acc = mt5.account_info()
    sym_info = mt5.symbol_info(symbol)
    if not acc or not sym_info:
        return 0.01

    equity = float(acc.equity)
    vol_min = float(sym_info.volume_min)
    vol_max = float(sym_info.volume_max)
    vol_step = float(sym_info.volume_step)
    point = float(sym_info.point)
    tick_value = float(sym_info.trade_tick_value)
    tick_size = float(sym_info.trade_tick_size)

    full_kelly = win_rate - ((1.0 - win_rate) / payoff_ratio)
    half_kelly = max(0.0, full_kelly / 2.0)
    risk_fraction = min(half_kelly * 0.05, max_risk_pct)
    dollar_risk = equity * risk_fraction

    sl_distance_points = abs(entry_price - sl_price) / point if sl_price > 0 else 350.0
    if sl_distance_points <= 0:
        sl_distance_points = 350.0

    point_value = (tick_value / tick_size) * point if tick_size > 0 else 1.0
    dollar_risk_per_lot = sl_distance_points * point_value

    if dollar_risk_per_lot <= 0:
        return vol_min

    raw_lots = dollar_risk / dollar_risk_per_lot
    stepped_lots = math.floor(raw_lots / vol_step) * vol_step
    final_lots = round(max(vol_min, min(stepped_lots, vol_max)), 2)
    return final_lots

import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

from silver_bullet_sniper import evaluate_silver_bullet, check_killzone, SilverBulletSetup
from sniper_execution_router import route_silver_bullet_order, load_engine_state, save_engine_state
from macro_news_shield import is_news_blackout
from execution_ledger import record_execution

LOG_PATH = Path(r"C:\Quant-Nexus-Eng\silver_bullet_daemon.log")
WATERMARK_FILE = Path(r"C:\Quant-Nexus-Eng\account_equity_watermark.json")
HEARTBEAT_FILE = Path(r"C:\Quant-Nexus-Eng\daemon_heartbeat.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("SilverBulletDaemon")

FLEET_SYMBOLS = ["GBPUSD", "EURUSD"]  # Hardened: FX Majors only, quarantined XAU/BTC/JPY
MT5_PATH = r"C:\MT5_Quant_278017866\terminal64.exe"
ACCOUNT = 278017866

MAX_DAILY_DRAWDOWN_PCT = 0.020
MAX_CONCURRENT_FLEET_TRADES = 2
MAX_USD_CORRELATED_TRADES = 1

USD_EXPOSURE_MAP = {
    "EURUSD": {"BUY": -1, "SELL": 1},
    "GBPUSD": {"BUY": -1, "SELL": 1},
    "XAUUSD": {"BUY": -1, "SELL": 1},
    "USDJPY": {"BUY": 1, "SELL": -1},
    "BTCUSD": {"BUY": 0, "SELL": 0},
    "GBPJPY": {"BUY": 0, "SELL": 0},
}

def init_mt5() -> bool:
    if not mt5.initialize(path=r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe", portable=False):
        log.error("Failed to connect to designated path: %s | Error: %s", MT5_PATH, mt5.last_error())
        return False

    acc = mt5.account_info()
    if not acc:
        log.error("Failed to query account info from %s", MT5_PATH)
        return False

    if not mt5.terminal_info():


        mt5.initialize(path=r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe", portable=False)


    mt5.login(login=278017866, password="H@ngkook3695", server="Exness-MT5Trial5")


    acc = mt5.account_info()


    if acc.login != ACCOUNT:
        log.critical("ACCOUNT SAFETY TRIP! Expected #%s but connected to #%s. Shutting down.", ACCOUNT, acc.login)
        mt5.shutdown()
        return False

    log.info("LOCKED ON TARGET TERMINAL: Account #%s (%s) | Balance: $%.2f | Equity: $%.2f",
             acc.login, acc.server, acc.balance, acc.equity)
    return True

def emit_heartbeat(status: str = "HEALTHY"):
    try:
        pulse = {
            "pid": os.getpid(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "account": ACCOUNT,
            "status": status,
            "monitored_fleet": len(FLEET_SYMBOLS)
        }
        temp_file = HEARTBEAT_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(pulse, indent=2), encoding="utf-8")
        temp_file.replace(HEARTBEAT_FILE)
    except Exception as e:
        log.warning("Heartbeat write failed: %s", e)

def get_daily_watermark(acc_info) -> dict:
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    state = {
        "date": today_str,
        "starting_equity": acc_info.equity,
        "consecutive_losses": 0,
        "cooldown_until": None,
        "circuit_breaker_tripped": False
    }
    if WATERMARK_FILE.exists():
        try:
            data = json.loads(WATERMARK_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today_str:
                state = data
        except Exception:
            pass
    WATERMARK_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state

def save_daily_watermark(state: dict):
    WATERMARK_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def check_circuit_breakers(acc_info) -> tuple[bool, str]:
    wm = get_daily_watermark(acc_info)
    now_utc = datetime.now(timezone.utc)
    if wm.get("cooldown_until"):
        cooldown_time = datetime.fromisoformat(wm["cooldown_until"])
        if now_utc < cooldown_time:
            rem_min = (cooldown_time - now_utc).total_seconds() / 60.0
            return False, f"CIRCUIT_COOLDOWN: Loss freeze ({rem_min:.1f}m remaining)"

    start_eq = wm.get("starting_equity", acc_info.equity)
    curr_eq = acc_info.equity
    daily_drawdown = (curr_eq - start_eq) / start_eq

    if daily_drawdown <= -MAX_DAILY_DRAWDOWN_PCT:
        wm["circuit_breaker_tripped"] = True
        save_daily_watermark(wm)
        return False, f"CIRCUIT_BREAKER_TRIPPED: Daily DD {daily_drawdown*100:.2f}% breached"

    return True, "CIRCUIT_HEALTHY"

def check_correlation_shield(new_setup: SilverBulletSetup, active_positions) -> tuple[bool, str]:
    if len(active_positions) >= MAX_CONCURRENT_FLEET_TRADES:
        return False, f"SHIELD_BLOCK: Fleet limit reached ({len(active_positions)}/{MAX_CONCURRENT_FLEET_TRADES})"

    new_usd_dir = USD_EXPOSURE_MAP.get(new_setup.symbol, {}).get(new_setup.direction, 0)
    if new_usd_dir == 0:
        return True, "SHIELD_CLEAR: Uncorrelated asset"

    current_usd_exposure = 0
    for pos in active_positions:
        sym = pos.symbol
        side = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        pos_usd_dir = USD_EXPOSURE_MAP.get(sym, {}).get(side, 0)
        current_usd_exposure += pos_usd_dir

    projected_usd_exposure = current_usd_exposure + new_usd_dir
    if abs(projected_usd_exposure) > MAX_USD_CORRELATED_TRADES:
        return False, f"SHIELD_BLOCK: USD correlation stacking risk (Net USD Dir: {projected_usd_exposure})"

    return True, "SHIELD_CLEAR"

def manage_open_trades():
    state = load_engine_state()
    active_trades = state.get("active_trades", {})
    if not active_trades:
        return

    positions = mt5.positions_get()
    live_tickets = {str(p.ticket): p for p in positions} if positions else {}

    modified = False
    for ticket_str, data in list(active_trades.items()):
        if ticket_str not in live_tickets:
            log.info("Ticket #%s closed on terminal. Purging from state.", ticket_str)
            del active_trades[ticket_str]
            modified = True
            continue

        pos = live_tickets[ticket_str]
        if data.get("be_moved", False):
            continue

        be_target = data["be_target"]
        direction = data["direction"]
        current_price = pos.price_current

        hit_be = (current_price >= be_target) if direction == "BUY" else (current_price <= be_target)
        if hit_be:
            new_sl = data["entry_price"]
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "sl": float(new_sl),
                "tp": float(pos.tp)
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                log.info("[TARGET REACHED] Break-Even locked on #%s (%s) at Entry: %.5f", ticket_str, pos.symbol, new_sl)
                data["be_moved"] = True
                modified = True
            else:
                log.warning("BE modification declined on #%s: %s", ticket_str, getattr(res, "comment", "error"))

    if modified:
        state["active_trades"] = active_trades
        save_engine_state(state)

def scan_and_execute(dry_run: bool = True):
    in_kz, kz_name = check_killzone()
    if not in_kz:
        return

    acc_info = mt5.account_info()
    if not acc_info:
        return

    cb_ok, cb_msg = check_circuit_breakers(acc_info)
    if not cb_ok:
        log.warning("Circuit Breaker Active: %s", cb_msg)
        return

    positions = mt5.positions_get()
    active_positions = list(positions) if positions else []

    for sym in FLEET_SYMBOLS:
        if any(p.symbol == sym for p in active_positions):
            continue

        news_locked, news_reason = is_news_blackout(sym)
        if news_locked:
            log.warning("Skipping %s: %s", sym, news_reason)
            continue

        sym_info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if not sym_info or not tick:
            continue

        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 35)
        if rates is None or len(rates) < 25:
            continue

        candles = [{"open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"]), "time": r["time"]} for r in rates]
        spread_pts = tick.ask - tick.bid

        t_signal = datetime.now(timezone.utc)
        setup = evaluate_silver_bullet(sym, candles, spread_pts=spread_pts, min_rr=2.0, enforce_sweep=True)
        if not setup:
            continue

        shield_ok, shield_msg = check_correlation_shield(setup, active_positions)
        if not shield_ok:
            log.warning("Shield Held: %s %s blocked (%s)", setup.symbol, setup.direction, shield_msg)
            continue

        log.info("[CONFLUENCE VERIFIED] %s %s | Sweep: %s @ %.5f | 50%% MT: %.5f", 
                 setup.symbol, setup.direction, setup.sweep.pool_type, setup.sweep.level, setup.entry_price)
        
        t_pre = time.perf_counter()
        ok, msg, details = route_silver_bullet_order(setup, dry_run=dry_run)
        t_post = time.perf_counter()
        latency_ms = (t_post - t_pre) * 1000.0

        if ok and not dry_run and "ticket" in details:
            try:
                record_execution(
                    ticket=details["ticket"],
                    symbol=setup.symbol,
                    direction=setup.direction,
                    killzone=setup.killzone,
                    volume=details.get("lots", calculate_half_kelly_lot(getattr(setup, "symbol", "USDJPY"), float(getattr(setup, "entry_price", 0.0)), float(getattr(setup, "stop_loss", getattr(setup, "sl", 0.0))))),
                    target_price=setup.entry_price,
                    fill_price=details.get("price", setup.entry_price),
                    point_size=sym_info.point,
                    spread_pts=spread_pts / sym_info.point,
                    signal_time=t_signal,
                    dispatch_latency_ms=latency_ms,
                    broker_ack_latency_ms=latency_ms,
                    broker_comment=msg
                )
            except Exception as e:
                log.warning("Ledger logging error: %s", e)

if __name__ == "__main__":
    is_dry = "--live" not in sys.argv
    log.info("QuantNexus Silver Bullet Daemon Initializing (Mode: %s)...", "DRY-RUN" if is_dry else "LIVE-ARMED")

    if not init_mt5():
        log.error("Designated MT5 terminal unreachable or account mismatch.")
        sys.exit(1)

    try:
        log.info("5s Surveillance active on Account #%s with Heartbeat & SQLite Ledger.", ACCOUNT)
        while True:
            emit_heartbeat("HEALTHY")
            manage_open_trades()
            scan_and_execute(dry_run=is_dry)
            time.sleep(5.0)
    except KeyboardInterrupt:
        log.info("Daemon stopped by operator.")
    finally:
        emit_heartbeat("STOPPED")
        mt5.shutdown()