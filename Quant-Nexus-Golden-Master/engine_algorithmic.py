import os
import sys
import time
import math
from datetime import datetime, timezone
import MetaTrader5 as mt5
from dotenv import load_dotenv

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import signature_engine
import matrix_resolver
import regime_engine
import spread_guard
from signal_notifier import broadcast_signal_with_alpha_badge

load_dotenv(override=True)

MAGIC_NUMBER = 100101
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]
TIMEFRAME = "M15"
BASE_RISK_PER_TRADE = 0.01  # 1.0% base equity risk per trade

def calculate_dynamic_lot_size(symbol: str, sl_points: float, position_multiplier: float) -> float:
    if position_multiplier <= 0.0:
        return 0.0

    account_info = mt5.account_info()
    sym_info = mt5.symbol_info(symbol)
    if not account_info or not sym_info:
        return 0.01

    equity = account_info.equity
    risk_capital = equity * BASE_RISK_PER_TRADE * position_multiplier

    point = sym_info.point
    tick_size = sym_info.trade_tick_size
    tick_value = sym_info.trade_tick_value

    if tick_size <= 0 or tick_value <= 0 or sl_points <= 0:
        return sym_info.volume_min

    loss_per_point_per_lot = (tick_value / tick_size) * point
    raw_lot = risk_capital / (sl_points * loss_per_point_per_lot)

    vol_step = sym_info.volume_step
    steps = round(raw_lot / vol_step)
    normalized_lot = steps * vol_step

    normalized_lot = max(sym_info.volume_min, min(sym_info.volume_max, normalized_lot))
    return round(normalized_lot, 2)

def evaluate_symbol_setup(symbol: str):
    tick = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    if not tick or not sym_info:
        return

    # --- GATE 1: SPREAD & LIQUIDITY GUARD ---
    liquidity = spread_guard.check_execution_spread_safety(symbol)
    if not liquidity["safe_to_execute"]:
        print(f"🚫 [{symbol}] Execution blocked by Spread Guard: {liquidity['reason']}")
        return

    # --- GATE 2: REGIME CONTEXT & NEWS VECTOR ---
    regime = regime_engine.evaluate_market_regime(symbol, mt5.TIMEFRAME_M15)
    if regime["position_multiplier"] <= 0.0:
        print(f"🛑 [{symbol}] {regime['warning']}")
        return

    # --- GATE 3: SIGNATURE & PATTERN CONFLUENCE ---
    sig = signature_engine.build_confluence_signature(symbol, TIMEFRAME)

    # --- GATE 4: PROBABILITY MATRIX & SCORE MODULATION ---
    raw_stats = matrix_resolver.query_confluence_probability(symbol, TIMEFRAME, sig)
    effective_score = regime_engine.modulate_quantum_score(raw_stats["win_rate"], regime)

    # Threshold: modulated score >= 60.0 required
    if effective_score >= 60.0:
        is_bullish = "BULLISH" in sig or "ABOVE_VWAP" in sig
        direction = "BUY" if is_bullish else "SELL"
        entry_price = tick.ask if direction == "BUY" else tick.bid

        point = sym_info.point
        risk_distance_points = 1500 * point if "XAU" in symbol else 150 * point
        reward_distance_points = risk_distance_points * raw_stats["avg_rr"]

        sl = entry_price - risk_distance_points if direction == "BUY" else entry_price + risk_distance_points
        tp = entry_price + reward_distance_points if direction == "BUY" else entry_price - reward_distance_points

        # Dynamic Volume Calculation
        trade_volume = calculate_dynamic_lot_size(
            symbol=symbol,
            sl_points=risk_distance_points / point,
            position_multiplier=regime["position_multiplier"]
        )

        if trade_volume <= 0.0:
            print(f"⚠️ [{symbol}] Volume calculated as 0.0. Trade aborted.")
            return

        print(f"🎯 [{symbol}] Signal: {sig} | Spread: {liquidity['current_spread']} pts | Lots: {trade_volume} | Score: {effective_score:.1f}")

        # Broadcast to Telegram with Alpha Badge + Regime Context
        broadcast_signal_with_alpha_badge(
            asset=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            trade_volume=trade_volume,
            quant_score=effective_score,
            timeframe=TIMEFRAME,
            explicit_signature=sig,
            regime_data=regime
        )

def engine_loop():
    print("🚀 Quant Nexus Algorithmic Engine Active.")
    print("🛡️ Spread Guard & Dynamic Regime Context Active.")
    while True:
        try:
            for symbol in SYMBOLS:
                evaluate_symbol_setup(symbol)
            time.sleep(30)
        except KeyboardInterrupt:
            print("\n🛑 Engine stopped cleanly.")
            break
        except Exception as e:
            print(f"⚠️ Engine loop error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    if mt5.initialize():
        engine_loop()
        mt5.shutdown()
