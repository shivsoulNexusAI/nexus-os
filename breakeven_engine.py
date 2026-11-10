from nexus_logging_guard import get_rotating_logger
"""
QUANTNEXUS BREAKEVEN & TRAILING STOP ENGINE (v1.0 Production Dry-Run)
Audits active positions across MT5, detects 1.5R expansion targets,
identifies M5 institutional liquidity swing pivots, and ratchets protective stops.
"""
import os
import gc
import sys
import time
import logging
from datetime import datetime, timezone
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_telegram import send_alert

LOG_PATH = r"C:\Quant-Nexus-Eng\breakeven_engine.log"
logger = get_rotating_logger("BreakevenEngine", "breakeven_engine.log")

MT5_PATH = r"C:\MT5_HFT_278041671\terminal64.exe"
POLL_CADENCE_SEC = 5
DRY_RUN = True  # Set to False for live execution modification

gc.set_threshold(700, 10, 5)

class BreakevenEngine:
    def __init__(self):
        # Maps ticket -> last ratcheted SL to avoid redundant modifications
        self.ratcheted_tickets = {}

    def get_m5_swing_pivot(self, symbol: str, pos_type: int) -> float:
        """
        Identifies the nearest confirmed M5 structural swing pivot.
        For BUY: Finds recent swing low across last 10 candles.
        For SELL: Finds recent swing high across last 10 candles.
        """
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 1, 10)
        if rates is None or len(rates) < 5:
            return 0.0

        if pos_type == mt5.ORDER_TYPE_BUY:
            swing_low = min(c['low'] for c in rates[-5:])
            return float(swing_low)
        else:
            swing_high = max(c['high'] for c in rates[-5:])
            return float(swing_high)

    def evaluate_positions(self):
        positions = mt5.positions_get()
        if positions is None or len(positions) == 0:
            return

        for pos in positions:
            ticket = pos.ticket
            symbol = pos.symbol
            pos_type = pos.type
            open_price = pos.price_open
            current_sl = pos.sl
            current_tp = pos.tp
            volume = pos.volume
            magic = pos.magic

            if current_sl <= 0.0:
                continue

            info = mt5.symbol_info(symbol)
            if not info:
                continue

            point = info.point
            spread = info.spread * point
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue

            current_price = tick.bid if pos_type == mt5.ORDER_TYPE_BUY else tick.ask

            r_risk = abs(open_price - current_sl)
            if r_risk <= 0.0:
                continue

            if pos_type == mt5.ORDER_TYPE_BUY:
                favorable_move = current_price - open_price
                current_r = favorable_move / r_risk
            else:
                favorable_move = open_price - current_price
                current_r = favorable_move / r_risk

            if current_r >= 1.5:
                swing_pivot = self.get_m5_swing_pivot(symbol, pos_type)

                if pos_type == mt5.ORDER_TYPE_BUY:
                    be_baseline = open_price + spread
                    proposed_sl = max(be_baseline, swing_pivot) if swing_pivot > 0 else be_baseline
                    proposed_sl = round(proposed_sl, info.digits)

                    if proposed_sl > current_sl and proposed_sl != self.ratcheted_tickets.get(ticket):
                        self._dispatch_ratchet(pos, current_price, current_r, proposed_sl, "BUY")

                elif pos_type == mt5.ORDER_TYPE_SELL:
                    be_baseline = open_price - spread
                    proposed_sl = min(be_baseline, swing_pivot) if swing_pivot > 0 else be_baseline
                    proposed_sl = round(proposed_sl, info.digits)

                    if (current_sl == 0.0 or proposed_sl < current_sl) and proposed_sl != self.ratcheted_tickets.get(ticket):
                        self._dispatch_ratchet(pos, current_price, current_r, proposed_sl, "SELL")

    def _dispatch_ratchet(self, pos, current_price, current_r, proposed_sl, direction: str):
        ticket = pos.ticket
        symbol = pos.symbol
        mode_str = "[DRY-RUN]" if DRY_RUN else "[LIVE-EXECUTION]"

        logger.info(
            f"{mode_str} 🎯 1.5R Expansion Detected on #{ticket} ({symbol} {direction}) | "
            f"Current R: {current_r:.2f}R | Price: {current_price} | "
            f"Old SL: {pos.sl} -> New Ratchet SL: {proposed_sl}"
        )

        if not DRY_RUN:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": symbol,
                "sl": proposed_sl,
                "tp": pos.tp,
                "magic": pos.magic
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                self.ratcheted_tickets[ticket] = proposed_sl
                logger.info(f"[SL-MODIFIED] #{ticket} successfully updated to SL: {proposed_sl}")
            else:
                logger.error(f"[SL-MOD-FAILED] #{ticket} retcode={getattr(res, 'retcode', None)}")
        else:
            self.ratcheted_tickets[ticket] = proposed_sl

        dry_badge = "🧪 <b>[DRY-RUN]</b> " if DRY_RUN else "🛡️ "
        send_alert(
            "quant_alert_bot",
            f"{dry_badge}<b>BREAKEVEN RATCHET TRIGGERED</b>\n"
            f"• Symbol: <code>{symbol}</code> ({direction}) | Ticket: <code>#{ticket}</code>\n"
            f"• Expansion: <b>+{current_r:.2f}R</b>\n"
            f"• Entry Price: <code>{pos.price_open}</code>\n"
            f"• Previous SL: <code>{pos.sl}</code>\n"
            f"• Ratcheted SL: <b><code>{proposed_sl}</code></b> (M5 Structural Pivot)\n"
            f"• Status: {'Simulated Modification' if DRY_RUN else 'Order Modified On Terminal'}"
        )

def main():
    logger.info(f"Starting Breakeven & Trailing Ratchet Engine (DRY_RUN={DRY_RUN})...")
    if not mt5.initialize(path=MT5_PATH):
        logger.error(f"Failed to initialize MT5 at {MT5_PATH}")
        return

    engine = BreakevenEngine()
    logger.info("Connected to MT5. Monitoring positions for 1.5R structural ratchets.")

    try:
        while True:
            engine.evaluate_positions()
            gc.collect()
            time.sleep(POLL_CADENCE_SEC)
    except KeyboardInterrupt:
        logger.info("Breakeven Engine halted by operator.")
    finally:
        mt5.shutdown()

if __name__ == '__main__':
    main()
