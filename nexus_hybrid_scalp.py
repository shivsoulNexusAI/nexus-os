import MetaTrader5 as mt5

class NexusHybridScalper:
    """
    Dual-Horizon Execution:
    Splits qualified setups into a Fast Scalp (60%) and a Macro Swing Runner (40%).
    """
    def __init__(self, scalp_split=0.60, min_rr_scalp=1.2, swing_rr=3.0):
        self.scalp_split = scalp_split
        self.min_rr_scalp = min_rr_scalp
        self.swing_rr = swing_rr

    def execute_dual_orders(self, symbol, order_type, total_lots, sl_price, entry_price):
        """
        Executes two linked orders:
        Order 1: Quick Scalp Take-Profit
        Order 2: Distant Swing Runner
        """
        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return False, "Symbol info missing"

        # Adaptive ATR / Risk distance calculation
        risk_dist = abs(entry_price - sl_price)
        if risk_dist <= 0:
            return False, "Invalid SL distance"

        # Scalp TP and Swing TP
        if order_type == mt5.ORDER_TYPE_BUY:
            scalp_tp = round(entry_price + (risk_dist * self.min_rr_scalp), sym_info.digits)
            swing_tp = round(entry_price + (risk_dist * self.swing_rr), sym_info.digits)
        else:
            scalp_tp = round(entry_price - (risk_dist * self.min_rr_scalp), sym_info.digits)
            swing_tp = round(entry_price - (risk_dist * self.swing_rr), sym_info.digits)

        step = sym_info.volume_step
        scalp_vol = round((total_lots * self.scalp_split) / step) * step
        scalp_vol = max(sym_info.volume_min, round(scalp_vol, 2))
        
        swing_vol = round((total_lots - scalp_vol) / step) * step
        swing_vol = max(sym_info.volume_min, round(swing_vol, 2))

        # 1. Fire Scalp Ticket
        scalp_req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": scalp_vol,
            "type": order_type,
            "price": entry_price,
            "sl": sl_price,
            "tp": scalp_tp,
            "deviation": 20,
            "magic": 999101,  # Scalp Magic Number
            "comment": "Nexus Scalp 60%",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res_scalp = mt5.order_send(scalp_req)

        # 2. Fire Swing Runner Ticket
        swing_req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": swing_vol,
            "type": order_type,
            "price": entry_price,
            "sl": sl_price,
            "tp": swing_tp,
            "deviation": 20,
            "magic": 999202,  # Swing Magic Number
            "comment": "Nexus Swing Core",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res_swing = mt5.order_send(swing_req)

        return True, f"Scalp: #{res_scalp.order} ({scalp_vol}L) | Swing: #{res_swing.order} ({swing_vol}L)"

    def synchronize_runner(self):
        """
        Monitors active trades. If the Scalp ticket has closed in profit,
        immediately moves the Swing runner ticket to Breakeven + buffer.
        """
        positions = mt5.positions_get()
        if not positions:
            return

        swing_positions = [p for p in positions if p.magic == 999202]
        scalp_positions = [p for p in positions if p.magic == 999101]

        # For every active swing runner without an active scalp sibling in the market
        for swing in swing_positions:
            sibling_scalp_open = any(s.symbol == swing.symbol for s in scalp_positions)
            
            # If the scalp is no longer open, it either TP'd or was closed
            if not sibling_scalp_open:
                sym_info = mt5.symbol_info(swing.symbol)
                # Check if SL is already at or beyond breakeven
                if swing.type == mt5.ORDER_TYPE_BUY and swing.sl < swing.price_open:
                    new_sl = round(swing.price_open + (10 * sym_info.point), sym_info.digits)
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": swing.ticket,
                        "symbol": swing.symbol,
                        "sl": new_sl,
                        "tp": swing.tp
                    })
                    print(f"[{swing.symbol}] Swing Runner #{swing.ticket} Secured to Breakeven!")
                elif swing.type == mt5.ORDER_TYPE_SELL and swing.sl > swing.price_open:
                    new_sl = round(swing.price_open - (10 * sym_info.point), sym_info.digits)
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": swing.ticket,
                        "symbol": swing.symbol,
                        "sl": new_sl,
                        "tp": swing.tp
                    })
                    print(f"[{swing.symbol}] Swing Runner #{swing.ticket} Secured to Breakeven!")
