from correlation_gate import CorrelationMatrixGate
from risk_allocator import VolatilityParityAllocator
"""
========================================================================================
 QUANTUM NEXUS // OMEGA-APEX UNIFIED AUTONOMOUS DAEMON
 Production Engine: Trailing Breaker + Macro VETO + ICT Imbalance + Kelly + FOK Execution
========================================================================================
"""
import os
import sys
import time
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
import requests
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

# Import Integrated Quantum Nexus Modules
from trailing_circuit_breaker import TrailingCircuitBreaker
from macro_regime_engine import MacroRegimeEngine
from ict_engine import ICTEngine
from cross_asset_risk_governor import CrossAssetRiskGovernor
from risk_allocator import kelly_allocator

# Force UTF-8 I/O for Windows Console Stability
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# --- CONFIGURATION & PATHS ---
BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master"
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOG_FILE = os.path.join(BASE_DIR, "daemon.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("OmegaApex")

# Default Parameters
LOGIN = 278017866
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"
TELEGRAM_BOT_TOKEN = "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw"
TELEGRAM_CHAT_ID = "5279761713"

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
EXECUTION_EDGE_THRESHOLD = 0.80

# Instantiate Core Engines
circuit_breaker = TrailingCircuitBreaker(base_floor=950.00, max_drawdown_pct=0.05)
macro_engine = MacroRegimeEngine(lookback_bars=48)
ict_engine = ICTEngine(fvg_min_points=10.0, sweep_lookback=20)
risk_governor = CrossAssetRiskGovernor(max_portfolio_risk_pct=0.04, single_trade_risk_pct=0.01)

# --- TELEGRAM TELEMETRY ---
def send_telegram(message: str):
    """Dispatches asynchronous formatted alert to Telegram."""
    if not TELEGRAM_BOT_TOKEN or "placeholder" in TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.warning(f"Telegram dispatch failed: {e}")

# --- MT5 TERMINAL HANDSHAKE ---
def init_mt5() -> bool:
    if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
        logger.critical(f"MT5 initialization failed: {mt5.last_error()}")
        return False
    if not mt5.login(login=LOGIN, password=PASSWORD, server=SERVER):
        logger.critical(f"MT5 login failed for #{LOGIN}: {mt5.last_error()}")
        return False
    logger.info(f"Connected to {SERVER} | Account #{LOGIN}")
    return True

# --- TECHNICAL ANALYSIS HELPERS ---
def get_atr(symbol: str, timeframe=mt5.TIMEFRAME_M5, period: int = 14) -> float:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 5)
    if rates is None or len(rates) < period:
        return 0.0
    df = pd.DataFrame(rates)
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum(np.abs(df['high'] - df['close'].shift(1)), 
                               np.abs(df['low'] - df['close'].shift(1)))).dropna()
    return float(tr.tail(period).mean())

def calculate_kaufman_er(symbol: str, timeframe=mt5.TIMEFRAME_M5, period: int = 10) -> float:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 2)
    if rates is None or len(rates) < period:
        return 0.0
    closes = np.array([r['close'] for r in rates])
    change = abs(closes[-1] - closes[-period])
    volatility = np.sum(np.abs(np.diff(closes[-period:])))
    return float(change / volatility) if volatility > 0 else 0.0

# --- FOK EXECUTION ENGINE ---
def get_symbol_filling_mode(sym_info) -> int:
    modes = sym_info.filling_mode
    if modes & 1:  # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    elif modes & 2:  # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

def execute_order(symbol: str, direction: str, volume: float, sl_points: float, tp_points: float) -> bool:
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        logger.error(f"Cannot execute {symbol}: Missing symbol info")
        return False

    filling = get_symbol_filling_mode(sym_info)
    pt = sym_info.point
    digits = sym_info.digits
    min_dist = max(sym_info.trade_stops_level, 5) * pt

    # Ensure sl_points and tp_points satisfy broker minimum distances
    sl_points = max(sl_points, min_dist)
    tp_points = max(tp_points, min_dist)

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            time.sleep(0.2)
            continue

        is_buy = (direction == "BUY")
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        entry_price = tick.ask if is_buy else tick.bid
        sl_price = entry_price - sl_points if is_buy else entry_price + sl_points
        tp_price = entry_price + tp_points if is_buy else entry_price - tp_points

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": entry_price,
            "sl": round(sl_price, digits),
            "tp": round(tp_price, digits),
            "deviation": 30,
            "magic": 888999,
            "comment": "OMEGA-APEX ELITE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling
        }

        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            msg = (
                f"🚀 <b>[ORDER FIRED]</b> #{res.order}\n"
                f"• Symbol   : <code>{symbol}</code>\n"
                f"• Direction: <b>{direction}</b>\n"
                f"• Volume   : <code>{volume}L</code>\n"
                f"• Entry    : <code>{entry_price:.5f}</code>\n"
                f"• SL / TP  : <code>{sl_price:.5f} / {tp_price:.5f}</code>"
            )
            logger.info(f"SUCCESS: Fired Ticket #{res.order} on {symbol} {direction} {volume}L (attempt {attempt})")
            send_telegram(msg)
            return True

        ret = res.retcode if res else mt5.last_error()
        comment = res.comment if res else "Unknown"
        logger.warning(f"Attempt {attempt}/{max_retries} failed for {symbol}: Retcode {ret} ({comment})")

        # Retryable retcodes: requote, price off, price change, connection glitch
        if ret in [10004, 10006, 10016, 10020, 10021]:
            time.sleep(0.3)
            continue
        else:
            break

    logger.error(f"Execution aborted for {symbol} after {max_retries} attempts.")
    return False

# --- MAIN ENGINE LIFECYCLE ---
def main():
    logger.info("Initializing Quantum Nexus: Omega-Apex Production Core...")
    if not init_mt5():
        sys.exit(1)

    while True:
        try:
            # 1. Evaluate Trailing Circuit Breaker Gate
            cb = circuit_breaker.evaluate()
            if not cb["allowed"]:
                logger.critical(f"CIRCUIT BREAKER LATCHED: {cb['reason']}")
                send_telegram(f"🚨 <b>CIRCUIT BREAKER TRIPPED</b>: {cb['reason']}")
                time.sleep(60)
                continue

            # 2. Evaluate Global Macro State
            macro = macro_engine.evaluate_macro_state()

            # 3. Symbol Scanning Pipeline
            candidates = []
            for sym in SYMBOLS:
                mt5.symbol_select(sym, True)
                tick = mt5.symbol_info_tick(sym)
                sym_info = mt5.symbol_info(sym)
                if not tick or not sym_info:
                    continue

                # Spread Friction Veto
                spread_points = (tick.ask - tick.bid)
                atr_m5 = get_atr(sym, mt5.TIMEFRAME_M5, 14)
                if atr_m5 <= 0 or (spread_points / atr_m5) > 0.20:
                    continue  # Spread is >20% of M5 bar range

                # Kaufman Efficiency (Regime)
                er = calculate_kaufman_er(sym, mt5.TIMEFRAME_M5, 10)
                base_bias = "BUY" if tick.bid > tick.ask - (spread_points * 2) else "SELL"
                base_edge = 0.50 + (er * 0.25)

                # ICT Engine Confluence
                ict = ict_engine.evaluate_ict_confluence(sym, mt5.TIMEFRAME_M5)
                direction = ict["bias"] if ict["bias"] != "FLAT" else base_bias
                total_edge = min(0.95, base_edge + ict["edge_boost"])

                candidates.append({
                    "symbol": sym,
                    "direction": direction,
                    "edge": total_edge,
                    "er": er,
                    "atr": atr_m5,
                    "ict_context": ict["reasons"]
                })

            # Sort by highest edge
            candidates.sort(key=lambda x: x["edge"], reverse=True)

            # Log Loop Telemetry
            top_cand = candidates[0] if candidates else None
            top_str = f"{top_cand['symbol']} {top_cand['direction']} ({top_cand['edge']*100:.1f}%)" if top_cand else "None"
            logger.info(
                f"[CYCLE] Floor: ${cb['floor']:.2f} (Buf: +${cb['buffer_usd']:.2f}) | "
                f"DXY: {macro.synthetic_dxy:.2f} [{macro.dxy_trend}] | Top: {top_str}"
            )
            # 4. Execution Candidate Evaluation
            for cand in candidates:
                sym = cand["symbol"]
                direction = cand["direction"]
                edge = cand["edge"]

                # Dynamic Threshold and Sizing Ceiling Synchronization
                try:
                    import json
                    with open('runtime_config.json', 'r', encoding='utf-8-sig') as f:
                        cfg = json.load(f)
                    gate = cfg.get("execution_edge_threshold", 0.75)
                    max_lot_cap = cfg.get("max_allowed_lots", {}).get(sym, cfg.get("default_max_lot", 0.05))
                except Exception:
                    gate = 0.75
                    max_lot_cap = 0.05

                if edge < gate:
                    continue

                # Volatility Bracket Geometry
                sl_dist = cand["atr"] * 1.5
                tp_dist = cand["atr"] * 3.0

                # Dynamic Quarter-Kelly Sizing (Signature Matched)
                acc = mt5.account_info()
                equity = acc.equity if acc else 1000.0
                rr = (tp_dist / sl_dist) if sl_dist > 0 else 2.0
                lots = kelly_allocator.calculate_lot_size(
                    symbol=sym,
                    equity=equity,
                    win_rate=edge,
                    rr_ratio=rr
                )

                if not lots or lots <= 0:
                    logger.warning(f"[{sym}] Sizing rejected: Calculated {lots}L below minimum threshold.")
                    continue

                # Apply Risk Sizing Ceiling
                lots = round(min(lots, max_lot_cap), 2)
                lots = max(0.01, lots)

                # Dispatch Execution
                logger.info(f"🎯 EDGE TRIGGER: {sym} {direction} @ {edge*100:.1f}% Edge | Sizing: {lots}L (Cap: {max_lot_cap}L)")
                success = execute_order(sym, direction, lots, sl_dist, tp_dist)
                if success:
                    time.sleep(10)
                    break
        except Exception as e:
            logger.error(f"Daemon exception caught: {e}", exc_info=True)

        time.sleep(60)

if __name__ == "__main__":
    main()
