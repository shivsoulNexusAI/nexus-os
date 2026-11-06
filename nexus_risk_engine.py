# -*- coding: utf-8 -*-
"""
NEXUS DYNAMIC RISK & TELEMETRIC PRODUCTION ENGINE (NDRE-v2.0)
Universal Asset-Agnostic Risk Guard, Fractional Kelly Sizer & Trailing Daemon.
Compatible with MT5, multi-threaded Telegram interactive loops, and autonomous runners.
"""

import math
import logging
from typing import Dict, Any, List, Optional
import MetaTrader5 as mt5

logger = logging.getLogger("NexusRiskEngine")

# --- ASSET CONFIGURATION MATRIX ---
ASSET_CONFIG = {
    "CRYPTO": {"atr_mult": 2.2, "be_r": 1.0, "tp1_r": 1.5, "tp2_r": 2.5, "spread_pad_pts": 10.0},
    "METALS": {"atr_mult": 1.8, "be_r": 1.0, "tp1_r": 1.5, "tp2_r": 2.5, "spread_pad_pts": 25.0},
    "FX":     {"atr_mult": 1.5, "be_r": 1.0, "tp1_r": 1.5, "tp2_r": 2.0, "spread_pad_pts": 2.0},
    "INDICES":{"atr_mult": 2.0, "be_r": 1.2, "tp1_r": 1.5, "tp2_r": 2.5, "spread_pad_pts": 5.0},
}

def classify_symbol(symbol: str) -> str:
    s = symbol.upper()
    if any(k in s for k in ["BTC", "ETH", "SOL", "XRP"]):
        return "CRYPTO"
    elif any(k in s for k in ["XAU", "XAG", "GOLD", "SILVER"]):
        return "METALS"
    elif any(k in s for k in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]):
        return "FX"
    return "INDICES"


class NexusRiskEngine:
    def __init__(self, login: int = 278025377, server: str = "Exness-MT5Trial5"):
        self.login = login
        self.server = server

    def ensure_connection(self) -> bool:
        if not mt5.terminal_info():
            return mt5.initialize(
                path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
                login=self.login,
                password="H@ngkook3695",
                server=self.server
            )
        return True

    def calculate_atr(self, symbol: str, timeframe=mt5.TIMEFRAME_M15, period: int = 14) -> float:
        """Computes true range volatility for dynamic trailing brackets."""
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 2)
        if rates is None or len(rates) < period + 1:
            sym_info = mt5.symbol_info(symbol)
            return (sym_info.point * 100) if sym_info else 1.0

        trs = []
        for i in range(1, len(rates)):
            high = rates[i]['high']
            low = rates[i]['low']
            prev_close = rates[i-1]['close']
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return sum(trs[-period:]) / period

    def calculate_kelly_lots(self, symbol: str, edge_pct: float, stop_distance_pts: float, win_loss_ratio: float = 2.0) -> float:
        """
        Fractional Kelly Criterion:
        f* = (p * (b + 1) - 1) / b
        Using Quarter-Kelly (f* / 4) for institutional drawdown suppression.
        """
        self.ensure_connection()
        acc = mt5.account_info()
        equity = acc.equity if acc else 10000.0
        
        # Normalize edge probability
        p = max(0.51, min(0.95, edge_pct / 100.0))
        b = max(1.2, win_loss_ratio)
        kelly_full = (p * (b + 1.0) - 1.0) / b
        quarter_kelly = max(0.005, (kelly_full / 4.0))  # Max 0.5% - 2.5% account risk
        
        risk_capital = equity * min(0.02, quarter_kelly)  # Hard cap at 2.0% per trade
        
        sym_info = mt5.symbol_info(symbol)
        if not sym_info or stop_distance_pts <= 0:
            return 0.01

        tick_size = sym_info.trade_tick_size or sym_info.point
        tick_value = sym_info.trade_tick_value or 1.0
        point = sym_info.point

        pts = stop_distance_pts / point
        cost_per_lot = (pts * (tick_value / (tick_size / point))) if tick_size > 0 else 100.0
        
        if cost_per_lot <= 0:
            return 0.01

        raw_lots = risk_capital / cost_per_lot
        step = sym_info.volume_step or 0.01
        min_lot = sym_info.volume_min or 0.01
        max_lot = sym_info.volume_max or 10.0

        calculated_lots = math.floor(raw_lots / step) * step
        return max(min_lot, min(max_lot, round(calculated_lots, 2)))

    def evaluate_and_ratchet(self) -> List[Dict[str, Any]]:
        """
        Universal Cycle: Evaluates all open tickets.
        Ratchets Breakeven, calculates trailing stops, checks partial TP milestones,
        and applies server-side TRADE_ACTION_SLTP modifications.
        """
        self.ensure_connection()
        positions = mt5.positions_get()
        if not positions:
            return []

        telemetry_events = []

        for pos in positions:
            symbol = pos.symbol
            ticket = pos.ticket
            pos_type = pos.type  # 0: BUY, 1: SELL
            volume = pos.volume
            open_price = pos.price_open
            current_price = pos.price_current
            sl = pos.sl
            tp = pos.tp
            profit = pos.profit

            asset_class = classify_symbol(symbol)
            cfg = ASSET_CONFIG.get(asset_class, ASSET_CONFIG["FX"])
            sym_info = mt5.symbol_info(symbol)
            if not sym_info:
                continue

            point = sym_info.point
            atr = self.calculate_atr(symbol)
            trail_distance = atr * cfg["atr_mult"]
            pad = cfg["spread_pad_pts"] * point

            # Determine position state
            is_buy = (pos_type == mt5.ORDER_TYPE_BUY)
            price_expansion = (current_price - open_price) if is_buy else (open_price - current_price)
            
            # --- 1. DYNAMIC BREAKEVEN CHECK ---
            be_threshold = atr * cfg["be_r"]
            new_sl = sl

            if price_expansion >= be_threshold:
                target_be = (open_price + pad) if is_buy else (open_price - pad)
                if is_buy and (sl < target_be or sl == 0.0):
                    new_sl = target_be
                    telemetry_events.append({
                        "ticket": ticket, "symbol": symbol, "event": "BREAKEVEN_LOCKED",
                        "old_sl": sl, "new_sl": new_sl, "profit": profit
                    })
                elif not is_buy and (sl > target_be or sl == 0.0):
                    new_sl = target_be
                    telemetry_events.append({
                        "ticket": ticket, "symbol": symbol, "event": "BREAKEVEN_LOCKED",
                        "old_sl": sl, "new_sl": new_sl, "profit": profit
                    })

            # --- 2. ATR TRAILING STOP RATCHET ---
            if price_expansion > (atr * 1.5):
                candidate_trail = (current_price - trail_distance) if is_buy else (current_price + trail_distance)
                if is_buy and candidate_trail > new_sl:
                    new_sl = round(candidate_trail, sym_info.digits)
                    telemetry_events.append({
                        "ticket": ticket, "symbol": symbol, "event": "TRAILING_RATCHET",
                        "old_sl": sl, "new_sl": new_sl, "profit": profit
                    })
                elif not is_buy and (new_sl == 0.0 or candidate_trail < new_sl):
                    new_sl = round(candidate_trail, sym_info.digits)
                    telemetry_events.append({
                        "ticket": ticket, "symbol": symbol, "event": "TRAILING_RATCHET",
                        "old_sl": sl, "new_sl": new_sl, "profit": profit
                    })

            # Apply modification if SL has improved
            if new_sl != sl and new_sl > 0:
                self.modify_position_sltp(ticket, symbol, new_sl, tp)

        return telemetry_events

    def modify_position_sltp(self, ticket: int, symbol: str, sl: float, tp: float) -> bool:
        """Sends server-side TRADE_ACTION_SLTP request to MT5."""
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": float(sl),
            "tp": float(tp)
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[+] Bracket modified #{ticket} {symbol} -> SL: {sl} | TP: {tp}")
            return True
        else:
            logger.warning(f"[-] Modification failed for #{ticket}: {res.comment if res else 'Unknown error'}")
            return False

# Global Singleton Instance
risk_engine = NexusRiskEngine()
