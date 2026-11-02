# -*- coding: utf-8 -*-
import math
import numpy as np
import MetaTrader5 as mt5

class ApexOmegaEngine:
    @staticmethod
    def analyze_asset(symbol: str):
        rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 50)
        rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 50)
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)

        if rates_m5 is None or rates_m1 is None or tick is None or info is None:
            return None

        spread = tick.ask - tick.bid
        atr = float(np.mean([r['high'] - r['low'] for r in rates_m5[-14:]]))
        if atr <= 0: atr = tick.bid * 0.001

        macro_high = max(r['high'] for r in rates_m5[-30:-3])
        macro_low = min(r['low'] for r in rates_m5[-30:-3])
        
        sweep_detected = None
        sweep_extreme = 0.0
        for r in rates_m5[-3:]:
            if r['low'] < macro_low:
                sweep_detected = 'BULLISH_SWEEP'
                sweep_extreme = r['low']
            elif r['high'] > macro_high:
                sweep_detected = 'BEARISH_SWEEP'
                sweep_extreme = r['high']

        mss_confirmed = False
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        signal_type = None
        noise_buffer = max(1.5 * atr, 4.0 * spread)

        if sweep_detected == 'BULLISH_SWEEP':
            m1_swing_high = max(r['high'] for r in rates_m1[-15:-3])
            m1_curr_close = rates_m1[-1]['close']
            if m1_curr_close > m1_swing_high:
                mss_confirmed = True
                signal_type = 'BUY'
                disp_low = min(r['low'] for r in rates_m1[-10:])
                entry_price = round(disp_low + ((m1_curr_close - disp_low) * 0.50), info.digits)
                sl_price = round(sweep_extreme - noise_buffer, info.digits)
                risk_pts = entry_price - sl_price
                tp_price = round(entry_price + (risk_pts * 2.2), info.digits)

        elif sweep_detected == 'BEARISH_SWEEP':
            m1_swing_low = min(r['low'] for r in rates_m1[-15:-3])
            m1_curr_close = rates_m1[-1]['close']
            if m1_curr_close < m1_swing_low:
                mss_confirmed = True
                signal_type = 'SELL'
                disp_high = max(r['high'] for r in rates_m1[-10:])
                entry_price = round(disp_high - ((disp_high - m1_curr_close) * 0.50), info.digits)
                sl_price = round(sweep_extreme + noise_buffer, info.digits)
                risk_pts = sl_price - entry_price
                tp_price = round(entry_price - (risk_pts * 2.2), info.digits)

        prob = 0.50
        if sweep_detected: prob += 0.08
        if mss_confirmed: prob += 0.15
        if spread > (atr * 0.4): prob -= 0.12
        prob = min(0.85, max(0.35, prob))

        return {
            'symbol': symbol,
            'bias': sweep_detected or 'BALANCED',
            'mss': mss_confirmed,
            'signal': signal_type if mss_confirmed and prob >= 0.65 else None,
            'prob': round(prob, 4),
            'entry': entry_price,
            'sl': sl_price,
            'tp': tp_price,
            'buffer': round(noise_buffer, info.digits)
        }
