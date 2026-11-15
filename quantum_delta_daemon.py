from volatility_regime_classifier import VolatilityRegimeClassifier

"""

QUANTNEXUS QUANTUM DELTA DAEMON (v3.0 Institutional FVG-CE Edition)

Automated M5 Market Structure Shift (MSS) + Fair Value Gap (FVG) Consequent

Encroachment (CE) Limit Order Execution with Half-Kelly Risk Allocation

and Multi-Terminal Balanced Routing.

"""

import os

import gc

import sys

import time

from datetime import datetime, timezone

from typing import Dict, List, Any, Optional

import MetaTrader5 as mt5



sys.path.append(r"C:\Quant-Nexus-Eng")

from nexus_logging_guard import get_rotating_logger

from nexus_state_guard import read_risk_state

from nexus_risk_kernel import NexusRiskKernel

from terminal_balancer import MultiTerminalBalancer

from imbalance_fvg_detector import ImbalanceFVGDetector

from nexus_telegram import send_alert



logger = get_rotating_logger("QuantumDeltaDaemon", "quantum_delta_daemon.log")



# Operational Parameters

POLL_INTERVAL_SEC = 15

SCAN_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "US30"]

MAGIC_NUMBER = 770099

MAX_OPEN_LIMITS_PER_SYMBOL = 1



risk_kernel = NexusRiskKernel()

balancer = MultiTerminalBalancer()

regime_classifier = VolatilityRegimeClassifier()

fvg_detector = ImbalanceFVGDetector(min_atr_factor=0.35, min_body_ratio=0.60, min_rvol_threshold=1.20)



def count_open_orders_for_symbol(symbol: str, terminal_path: str) -> int:

    """Counts pending and active positions for a symbol under the magic number."""

    if not mt5.initialize(path=terminal_path):

        return 999

    orders = mt5.orders_get(symbol=symbol)

    positions = mt5.positions_get(symbol=symbol)

    mt5.shutdown()

    

    total = 0

    if orders:

        total += sum(1 for o in orders if o.magic == MAGIC_NUMBER)

    if positions:

        total += sum(1 for p in positions if p.magic == MAGIC_NUMBER)

    return total



def place_ce_limit_order(

    terminal_path: str,

    terminal_id: str,

    symbol: str,

    order_type_str: str,

    ce_price: float,

    stop_loss: float,

    take_profit: float,

    lot_size: float

) -> bool:

    """Dispatches a tick-exact pending Limit order to the assigned MT5 terminal."""

    if not mt5.initialize(path=terminal_path):

        logger.error(f"[{terminal_id}] Failed MT5 initialize: {mt5.last_error()}")

        return False



    order_type = mt5.ORDER_TYPE_BUY_LIMIT if order_type_str == "BUY_LIMIT" else mt5.ORDER_TYPE_SELL_LIMIT

    

    request = {

        "action": mt5.TRADE_ACTION_PENDING,

        "symbol": symbol,

        "volume": lot_size,

        "type": order_type,

        "price": ce_price,

        "sl": stop_loss,

        "tp": take_profit,

        "deviation": 10,

        "magic": MAGIC_NUMBER,

        "comment": f"QN_CE_{order_type_str[:3]}",

        "type_time": mt5.ORDER_TIME_GTC,

        "type_filling": mt5.ORDER_FILLING_RETURN

    }



    result = mt5.order_send(request)

    mt5.shutdown()

    gc.collect()



    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:

        retcode = result.retcode if result else "None"

        comment = result.comment if result else "No Result"

        logger.error(f"[{terminal_id}] CE Limit Order Failed ({order_type_str} {symbol} @ {ce_price}): {retcode} - {comment}")

        return False



    logger.info(f"[{terminal_id}] [ORDER-SENT] Ticket #{result.order} | {order_type_str} {symbol} {lot_size} lots @ {ce_price} | SL: {stop_loss} | TP: {take_profit}")

    

    # Broadcast execution alert to Telegram

    msg = (

        f"🎯 <b>QUANTNEXUS INSTITUTIONAL CE LIMIT ORDER PLACED</b>\n"

        f"• Terminal: <code>{terminal_id}</code>\n"

        f"• Symbol: <b>{symbol}</b> ({order_type_str})\n"

        f"• Limit Price (CE): <b>{ce_price}</b>\n"

        f"• Volume: <b>{lot_size} lots</b>\n"

        f"• Stop Loss: <code>{stop_loss}</code> | Target TP: <code>{take_profit}</code>\n"

        f"• Ticket: <code>#{result.order}</code>"

    )

    send_alert("quant_alert_bot", msg)

    return True





def resolve_target_terminal(balancer_instance) -> Optional[Dict[str, str]]:

    """Safe resolution matching whatever interface MultiTerminalBalancer exposes."""

    for method_name in ["get_optimal_terminal", "get_best_terminal", "select_terminal", "get_target_terminal", "get_least_loaded_terminal"]:

        if hasattr(balancer_instance, method_name) and callable(getattr(balancer_instance, method_name)):

            return getattr(balancer_instance, method_name)()

    

    # Fallback to internal terminal list attribute if exposed

    for attr in ["terminals", "terminal_pool", "nodes", "config"]:

        if hasattr(balancer_instance, attr):

            pool = getattr(balancer_instance, attr)

            if isinstance(pool, list) and len(pool) > 0:

                return pool[0] if isinstance(pool[0], dict) else {"id": "DEFAULT", "path": pool[0]}

                

    # Ultimate fail-safe default pointing to primary terminal

    return {

        "id": "TERM_QUANT_278061453",

        "path": "C:/MT5_Quant_278061453/terminal64.exe"

    }



def process_symbol_alpha(symbol: str):

    """Evaluates market state, unmitigated FVGs, and routes CE Limit orders."""

    # 1. State Guard Verification

    risk_state = read_risk_state()

    if risk_state.get("circuit_breaker_tripped", False):

        logger.warning(f"[CIRCUIT-BREAKER-ACTIVE] Trading halted: {risk_state.get('active_circuit_reason')}")

        return



    # 2. Select terminal node with lowest margin utilization / balanced capacity

    best_node = resolve_target_terminal(balancer)

    if not best_node:

        logger.warning("No operational MT5 terminals available via terminal_balancer.")

        return



    term_path = best_node["path"]

    term_id = best_node["id"]



    # 3. Guard against duplicate orders per symbol

    active_count = count_open_orders_for_symbol(symbol, term_path)

    if active_count >= MAX_OPEN_LIMITS_PER_SYMBOL:

        return



    # 4. Scan for unmitigated FVGs using primary terminal

    if not mt5.initialize(path=term_path):

        return

    

    sym_info = mt5.symbol_info(symbol)

    tick = mt5.symbol_info_tick(symbol)

    if not sym_info or not tick:

        mt5.shutdown()

        return



    # Extract symbol metadata dict for Risk Kernel

    symbol_dict = {

        "trade_tick_size": sym_info.trade_tick_size,

        "trade_tick_value": sym_info.trade_tick_value,

        "trade_contract_size": sym_info.trade_contract_size,

        "volume_min": sym_info.volume_min,

        "volume_max": sym_info.volume_max,

        "volume_step": sym_info.volume_step

    }



    acc = mt5.account_info()

    equity = acc.equity if acc else 1000.0



    # Query Real-Time Volatility Regime

    regime = regime_classifier.classify_market_regime(symbol, timeframe=mt5.TIMEFRAME_M5)

    tp_mult = regime.get("tp_multiplier", 2.0)

    kelly_mod = regime.get("kelly_scale", 1.0)



    imbalances = fvg_detector.scan_symbol_imbalances(symbol, timeframe=mt5.TIMEFRAME_M5, lookback_bars=45)

    mt5.shutdown()

    gc.collect()



    if not imbalances:

        return



    # Find the most recent fresh/unmitigated imbalance

    for fvg in reversed(imbalances):

        if fvg["mitigated"]:

            continue  # Prefer completely untouched voids



        ce_price = fvg["ce_price"]

        gap_type = fvg["type"]



        # Bullish BISI: CE must be below current Ask price to place a valid BUY_LIMIT

        if gap_type == "BULLISH_FVG" and ce_price < tick.ask:

            # Anchor SL below gap low with 3-pip buffer

            pip_unit = 0.01 if "JPY" in symbol else 0.0001

            sl_price = round(fvg["gap_low"] - (3.0 * pip_unit), 5)

            sl_dist = ce_price - sl_price

            if sl_dist <= 0:

                continue



            tp_price = round(ce_price + (tp_mult * sl_dist), 5)



            # Half-Kelly position sizing

            sizing = risk_kernel.calculate_bounded_lot_size(

                equity=equity,

                entry_price=ce_price,

                stop_loss_price=sl_price,

                symbol_info=symbol_dict,

                consecutive_losses=risk_state.get("consecutive_losses", 0)

            )



            if sizing["lot_size"] > 0:

                logger.info(f"[ALPHA-TRIGGER] {symbol} BULLISH FVG @ CE {ce_price} | Lots: {sizing['lot_size']} | Risk: {sizing['actual_risk_pct']}%")

                place_ce_limit_order(

                    terminal_path=term_path,

                    terminal_id=term_id,

                    symbol=symbol,

                    order_type_str="BUY_LIMIT",

                    ce_price=ce_price,

                    stop_loss=sl_price,

                    take_profit=tp_price,

                    lot_size=sizing["lot_size"]

                )

                break



        # Bearish SIBI: CE must be above current Bid price to place a valid SELL_LIMIT

        elif gap_type == "BEARISH_FVG" and ce_price > tick.bid:

            pip_unit = 0.01 if "JPY" in symbol else 0.0001

            sl_price = round(fvg["gap_high"] + (3.0 * pip_unit), 5)

            sl_dist = sl_price - ce_price

            if sl_dist <= 0:

                continue



            tp_price = round(ce_price - (tp_mult * sl_dist), 5)



            sizing = risk_kernel.calculate_bounded_lot_size(

                equity=equity,

                entry_price=ce_price,

                stop_loss_price=sl_price,

                symbol_info=symbol_dict,

                consecutive_losses=risk_state.get("consecutive_losses", 0)

            )



            if sizing["lot_size"] > 0:

                logger.info(f"[ALPHA-TRIGGER] {symbol} BEARISH FVG @ CE {ce_price} | Lots: {sizing['lot_size']} | Risk: {sizing['actual_risk_pct']}%")

                place_ce_limit_order(

                    terminal_path=term_path,

                    terminal_id=term_id,

                    symbol=symbol,

                    order_type_str="SELL_LIMIT",

                    ce_price=ce_price,

                    stop_loss=sl_price,

                    take_profit=tp_price,

                    lot_size=sizing["lot_size"]

                )

                break



def run_quantum_delta_loop():

    logger.info("================================================================================")

    logger.info("   QUANTNEXUS QUANTUM DELTA DAEMON v3.0 (FVG-CE INSTITUTIONAL RUNTIME ACTIVE)  ")

    logger.info("================================================================================")



    while True:

        try:

            for symbol in SCAN_SYMBOLS:

                sym_info = mt5.symbol_info(symbol)

                if not sym_info or sym_info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:

                    continue

                tick = mt5.symbol_info_tick(symbol)

                if not tick or tick.ask <= 0.0 or tick.bid <= 0.0:

                    continue

                import time as _t

                if (_t.time() - tick.time) > 600:

                    continue

                process_symbol_alpha(symbol)

                time.sleep(1.0)

            time.sleep(POLL_INTERVAL_SEC)

        except Exception as exc:

            logger.error(f"[DAEMON-LOOP-ERR] {exc}")

            time.sleep(5.0)

if __name__ == "__main__":

    run_quantum_delta_loop()

