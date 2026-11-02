"""
Quant Nexus: Elite Omega Engine
Module: omega_atr_stepper.py
Description: Dynamic ATR-based trailing stop and profit ladder lock engine.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np


class OmegaAtrStepper:
    def __init__(self, atr_period: int = 14, atr_multiplier: float = 1.2, be_trigger_r: float = 1.5):
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.be_trigger_r = be_trigger_r

    def calculate_atr(self, symbol: str, timeframe=mt5.TIMEFRAME_M5) -> float:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, self.atr_period + 5)
        if rates is None or len(rates) < self.atr_period:
            return 0.0

        df = pd.DataFrame(rates)
        df["prev_close"] = df["close"].shift(1)
        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = (df["high"] - df["prev_close"]).abs()
        df["tr3"] = (df["low"] - df["prev_close"]).abs()
        df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)

        atr = df["tr"].rolling(self.atr_period).mean().iloc[-1]
        return float(atr)

    def audit_and_trail_positions(self) -> list:
        positions = mt5.positions_get()
        if not positions:
            return []

        actions = []
        for p in positions:
            symbol = p.symbol
            ticket = p.ticket
            entry = p.price_open
            current_sl = p.sl
            current_price = p.price_current
            pos_type = p.type
            point = mt5.symbol_info(symbol).point

            atr = self.calculate_atr(symbol)
            if atr == 0.0:
                continue

            risk_dist = abs(entry - current_sl) if current_sl > 0 else (250 * point)
            if risk_dist == 0:
                risk_dist = 250 * point

            if pos_type == mt5.ORDER_TYPE_BUY:
                floating_gain = current_price - entry
                r_multiple = floating_gain / risk_dist

                if r_multiple >= self.be_trigger_r and (current_sl < entry or current_sl == 0):
                    new_sl = round(entry + (10 * point), mt5.symbol_info(symbol).digits)
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": ticket,
                        "sl": new_sl,
                        "tp": p.tp
                    }
                    res = mt5.order_send(req)
                    actions.append(f"#{ticket} {symbol} BUY SL stepped to Breakeven+1 ({new_sl}) | RetCode: {res.retcode}")

                elif r_multiple >= 2.5:
                    trail_target = round(current_price - (atr * self.atr_multiplier), mt5.symbol_info(symbol).digits)
                    if trail_target > current_sl and trail_target > entry:
                        req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": trail_target,
                            "tp": p.tp
                        }
                        res = mt5.order_send(req)
                        actions.append(f"#{ticket} {symbol} BUY ATR Trailed to {trail_target} | RetCode: {res.retcode}")

            elif pos_type == mt5.ORDER_TYPE_SELL:
                floating_gain = entry - current_price
                r_multiple = floating_gain / risk_dist

                if r_multiple >= self.be_trigger_r and (current_sl > entry or current_sl == 0):
                    new_sl = round(entry - (10 * point), mt5.symbol_info(symbol).digits)
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": ticket,
                        "sl": new_sl,
                        "tp": p.tp
                    }
                    res = mt5.order_send(req)
                    actions.append(f"#{ticket} {symbol} SELL SL stepped to Breakeven+1 ({new_sl}) | RetCode: {res.retcode}")

                elif r_multiple >= 2.5:
                    trail_target = round(current_price + (atr * self.atr_multiplier), mt5.symbol_info(symbol).digits)
                    if (current_sl == 0 or trail_target < current_sl) and trail_target < entry:
                        req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": trail_target,
                            "tp": p.tp
                        }
                        res = mt5.order_send(req)
                        actions.append(f"#{ticket} {symbol} SELL ATR Trailed to {trail_target} | RetCode: {res.retcode}")

        return actions