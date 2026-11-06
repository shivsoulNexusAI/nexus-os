import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

class NexusOmegaEngine:
    """
    Institutional Multi-Timeframe ICT & Order Flow Execution Engine.
    Enforces Macro Bias, Liquidity Sweeps, Dynamic Risk, and Multi-Stage Exits.
    """
    def __init__(self, risk_pct=0.015, min_rr=2.0):
        self.risk_pct = risk_pct          # 1.5% max risk per execution
        self.min_rr = min_rr              # Minimum 1:2 Risk-to-Reward
        
    def get_htf_bias(self, symbol):
        """
        Evaluates H1 market structure via EMA alignment and swing breakouts.
        Returns 'BULLISH', 'BEARISH', or 'NEUTRAL'.
        """
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
        if rates is None or len(rates) < 50:
            return "NEUTRAL"
            
        df = pd.DataFrame(rates)
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        if last['close'] > last['ema20'] > last['ema50'] and last['close'] >= prev['high']:
            return "BULLISH"
        elif last['close'] < last['ema20'] < last['ema50'] and last['close'] <= prev['low']:
            return "BEARISH"
        return "NEUTRAL"

    def detect_liquidity_sweep(self, symbol, htf_bias):
        """
        Inspects M5 timeframe for external range liquidity sweep and MSS displacement.
        """
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 30:
            return False, 0.0, 0.0

        df = pd.DataFrame(rates)
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        recent_low = np.min(lows[-15:-3])
        recent_high = np.max(highs[-15:-3])
        
        current_low = lows[-1]
        current_high = highs[-1]
        current_close = closes[-1]

        # Bullish Setup: Sweep of recent lows + strong displacement close back inside
        if htf_bias == "BULLISH":
            if current_low < recent_low and current_close > recent_low:
                sl_price = round(current_low - (10 * mt5.symbol_info(symbol).point), mt5.symbol_info(symbol).digits)
                tp_dist = (current_close - sl_price) * self.min_rr
                tp_price = round(current_close + tp_dist, mt5.symbol_info(symbol).digits)
                return True, sl_price, tp_price

        # Bearish Setup: Sweep of recent highs + strong displacement close below
        elif htf_bias == "BEARISH":
            if current_high > recent_high and current_close < recent_high:
                sl_price = round(current_high + (10 * mt5.symbol_info(symbol).point), mt5.symbol_info(symbol).digits)
                tp_dist = (sl_price - current_close) * self.min_rr
                tp_price = round(current_close - tp_dist, mt5.symbol_info(symbol).digits)
                return True, sl_price, tp_price

        return False, 0.0, 0.0

    def compute_position_size(self, symbol, sl_price):
        """
        Computes exact lot size based on account balance and structural SL distance.
        """
        acc = mt5.account_info()
        sym = mt5.symbol_info(symbol)
        if not acc or not sym:
            return 0.01

        balance = acc.balance
        risk_cash = balance * self.risk_pct
        current_price = sym.bid
        
        sl_distance = abs(current_price - sl_price)
        if sl_distance <= 0:
            return sym.volume_min

        # Point value conversion
        tick_value = sym.trade_tick_value
        tick_size = sym.trade_tick_size
        if tick_value == 0 or tick_size == 0:
            return sym.volume_min

        points_risked = sl_distance / tick_size
        lot_size = risk_cash / (points_risked * tick_value)
        
        # Clamp to broker limits
        lot_step = sym.volume_step
        lot_size = round(lot_size / lot_step) * lot_step
        return max(sym.volume_min, min(sym.volume_max, round(lot_size, 2)))

    def partial_close(self, ticket, fraction=0.5):
        """
        Closes a fraction of the open lot volume to secure real bank profit.
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        p = pos[0]
        sym = mt5.symbol_info(p.symbol)
        close_vol = round(p.volume * fraction, 2)
        if close_vol < sym.volume_min:
            return False

        order_type = mt5.ORDER_TYPE_BUY if p.type == 1 else mt5.ORDER_TYPE_SELL
        price = sym.ask if order_type == mt5.ORDER_TYPE_BUY else sym.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": p.symbol,
            "volume": close_vol,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 888001,
            "comment": f"Partial Bank {int(fraction*100)}%",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        return res.retcode == mt5.TRADE_RETCODE_DONE
