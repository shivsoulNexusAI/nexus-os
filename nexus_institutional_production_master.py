import time
import math
import logging
from datetime import datetime, timezone
import MetaTrader5 as mt5
from apex_ml_feature_engine import ApexMicrostructureML

# ==============================================================================
# INSTITUTIONAL SPECIFICATION & PARAMETERS
# ==============================================================================
ACCOUNT_LOGIN = 278029146
ACCOUNT_SERVER = "Exness-MT5Trial5"
ACCOUNT_PASSWORD = "H@ngkook3695"
MT5_PATH         = r"C:\Program Files\MetaTrader 5\terminal64.exe"

SYMBOLS          = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "USDJPY"]
SCAN_INTERVAL_SEC = 30

# Asymmetric Dynamic Half-Kelly Engine
KELLY_LAMBDA     = 0.50    # Half-Kelly safety factor
MAX_RISK_CAP     = 0.025   # Hard 2.50% equity cap ($233 max risk on $9.3k)
MIN_RISK_FLOOR   = 0.0025  # 0.25% floor
ML_PROB_HURDLE   = 0.65    # Minimum ML win probability to authorize execution
REWARD_RATIO_B   = 2.00    # Asymmetric 2:1 target

# Execution & Microstructure Guards
SPREAD_RATIO_MAX = 2.50    # Jump-diffusion blowout filter
KRONOS_MAX_MINS  = 60.0    # 12-bar (M5) temporal decay exit limit
MAX_CONCURRENT   = 2       # Portfolio VaR concurrency cap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(r"C:\Quant-Nexus-Eng\production_institutional.log", mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("NEXUS_CORE")

def ensure_mt5_connected():
    if not mt5.terminal_info() or not mt5.account_info() or mt5.account_info().login != ACCOUNT_LOGIN:
        log.info(f"Binding MT5 session to Account: {ACCOUNT_LOGIN} ({ACCOUNT_SERVER})")
        if not mt5.initialize(path=MT5_PATH, login=ACCOUNT_LOGIN, password=ACCOUNT_PASSWORD, server=ACCOUNT_SERVER, portable=True, timeout=60000):
            log.error(f"MT5 Init Failure: {mt5.last_error()}")
            return False
    return True

def get_symbol_filling_mode(symbol: str):
    info = mt5.symbol_info(symbol)
    if not info:
        return mt5.ORDER_FILLING_FOK
    modes = info.filling_mode
    if modes & 2:
        return mt5.ORDER_FILLING_IOC
    elif modes & 1:
        return mt5.ORDER_FILLING_FOK
    else:
        return mt5.ORDER_FILLING_RETURN

# ==============================================================================
# SUB-SYSTEM: KRONOS TEMPORAL ALPHA DECAY
# ==============================================================================
class KronosRegimeEngine:
    @staticmethod
    def audit_decay():
        if not ensure_mt5_connected():
            return

        positions = mt5.positions_get()
        if not positions:
            return

        for p in positions:
            pos_time = datetime.fromtimestamp(p.time, timezone.utc)
            duration_minutes = (datetime.now(timezone.utc) - pos_time).total_seconds() / 60.0

            # Exit if position stalls across 12 bars (60 min) with flat PnL (< $10)
            if duration_minutes >= KRONOS_MAX_MINS and abs(p.profit) < 10.0:
                log.info(f"[KRONOS DECAY] Ticket #{p.ticket} ({p.symbol}) flat after {duration_minutes:.1f}m. Recycling capital.")
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                tick = mt5.symbol_info_tick(p.symbol)
                price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "type": close_type,
                    "price": price,
                    "deviation": 20,
                    "magic": 999888,
                    "comment": "Kronos Temporal Exit",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": get_symbol_filling_mode(p.symbol),
                }
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log.info(f"Closed #{p.ticket} via Kronos Alpha Decay Guard.")

# ==============================================================================
# SUB-SYSTEM: APEX ML-SCALED HALF-KELLY EXECUTION
# ==============================================================================
def calculate_ml_half_kelly_lot(symbol: str, p_hat: float, stop_distance_pts: float, equity: float):
    # Dynamic Kelly: f* = (p(b+1) - 1) / b * lambda
    raw_kelly = (p_hat * (REWARD_RATIO_B + 1.0) - 1.0) / REWARD_RATIO_B
    if raw_kelly <= 0:
        return 0.0

    scaled_risk = max(MIN_RISK_FLOOR, min(MAX_RISK_CAP, raw_kelly * KELLY_LAMBDA))
    dollar_risk = equity * scaled_risk

    info = mt5.symbol_info(symbol)
    if not info:
        return 0.0

    point = info.point
    tick_val = info.trade_tick_value
    tick_sz = info.trade_tick_size

    if tick_val <= 0 or tick_sz <= 0:
        tick_val = 1.0
        tick_sz = point

    pts_per_tick = tick_sz / point if point > 0 else 1.0
    val_per_point_1lot = tick_val / pts_per_tick if pts_per_tick > 0 else 1.0

    risk_per_1lot = stop_distance_pts * val_per_point_1lot
    if risk_per_1lot <= 0:
        return info.volume_min

    raw_vol = dollar_risk / risk_per_1lot
    step = info.volume_step
    vol = math.floor(raw_vol / step) * step
    return max(info.volume_min, min(info.volume_max, round(vol, 2)))

def execute_apex_ml_order(symbol: str, bias: str, p_hat: float, atr: float, equity: float):
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not info or not tick:
        return

    is_buy = "BULLISH" in bias
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    entry_price = tick.ask if is_buy else tick.bid

    sl_pts = max(atr * 1.5, 300 * info.point) / info.point
    lot = calculate_ml_half_kelly_lot(symbol, p_hat, sl_pts, equity)

    if lot <= 0:
        log.info(f"? Sizing Veto: Kelly lot resolved to 0 for {symbol} (p_hat: {p_hat:.2f})")
        return

    sl = entry_price - (sl_pts * info.point) if is_buy else entry_price + (sl_pts * info.point)
    tp = entry_price + (sl_pts * REWARD_RATIO_B * info.point) if is_buy else entry_price - (sl_pts * REWARD_RATIO_B * info.point)

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": entry_price,
        "sl": round(sl, info.digits),
        "tp": round(tp, info.digits),
        "deviation": 20,
        "magic": 999888,
        "comment": f"ApexML [{p_hat:.2f}]",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_symbol_filling_mode(symbol),
    }

    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"EXECUTED: {symbol} {bias} | Lots: {lot} | P(Win): {p_hat:.1%} | Ticket: {res.order}")
    else:
        comment = res.comment if res else "None"
        code = res.retcode if res else "None"
        log.warning(f"Execution failed for {symbol}: Retcode {code} | {comment}")

# ==============================================================================
# MAIN PRODUCTION RUNNER
# ==============================================================================
def run_production():
    log.info("=" * 75)
    log.info("QUANT NEXUS APEX ML FLEET - AUTONOMOUS 24/7 PRODUCTION CORE")
    log.info(f"Account: {ACCOUNT_LOGIN} | Machine Learning Sizing: Dynamic Half-Kelly")
    log.info(f"Hurdle: P(Win) >= {ML_PROB_HURDLE*100:.0f}% | Max Risk Cap: {MAX_RISK_CAP*100}% | Concurrency: {MAX_CONCURRENT}")
    log.info("=" * 75)

    while True:
        try:
            if not ensure_mt5_connected():
                time.sleep(10)
                continue

            acc = mt5.account_info()
            equity = acc.equity

            # Run Kronos Temporal Decay Audit
            KronosRegimeEngine.audit_decay()

            open_positions = mt5.positions_get()
            open_count = len(open_positions) if open_positions else 0
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            log.info(f"\n--- [APEX ML SCAN] {now_str} | Equity: ${equity:,.2f} | Open: {open_count}/{MAX_CONCURRENT} ---")

            for sym in SYMBOLS:
                ml_res = ApexMicrostructureML.extract_features(sym)
                if not ml_res:
                    continue

                bias = ml_res["bias"]
                p_hat = ml_res["probability"]
                ofi = ml_res["ofi"]
                spread_ratio = ml_res["spread_ratio"]
                atr = ml_res["atr"]

                status_icon = "QUALIFIED" if p_hat >= ML_PROB_HURDLE and spread_ratio <= SPREAD_RATIO_MAX and bias != "NEUTRAL" else "MONITORING"
                log.info(f"[{status_icon:<10}] {sym:<7} | Bias: {bias:<14} | P(Win): {p_hat*100:>5.1f}% | OFI: {ofi:>+5.2f} | SpreadRatio: {spread_ratio:.2f}x")

                # Concurrency, Hurdle, and Spread Gates
                if open_count < MAX_CONCURRENT and p_hat >= ML_PROB_HURDLE and bias != "NEUTRAL":
                    if spread_ratio > SPREAD_RATIO_MAX:
                        log.warning(f"SPREAD GUARD: {sym} blocked. Ratio {spread_ratio:.2f}x > {SPREAD_RATIO_MAX}x")
                    else:
                        sym_active = any(p.symbol == sym for p in open_positions) if open_positions else False
                        if not sym_active:
                            execute_apex_ml_order(sym, bias, p_hat, atr, equity)

        except Exception as e:
            log.error(f"Production loop error: {str(e)}", exc_info=True)

        time.sleep(SCAN_INTERVAL_SEC)

if __name__ == "__main__":
    run_production()
