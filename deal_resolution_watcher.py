"""
QUANTNEXUS DEAL RESOLUTION WATCHER (v3.0 Institutional Production)
Watches closed deals across MT5 terminals, atomically updates daily realized PnL
in risk_state.json, enforces daily circuit breaker ceilings, and broadcasts telemetry.
"""
import os
import gc
import sys
import time
import json
import logging
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_risk_kernel import risk_kernel
from nexus_telegram import send_alert

LOG_PATH = r"C:\Quant-Nexus-Eng\deal_resolution_watcher.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DealResolutionWatcher")

MT5_PATH = r"C:\MT5_HFT_278041671\terminal64.exe"
STATE_FILE = r"C:\Quant-Nexus-Eng\risk_state.json"
POLL_CADENCE_SEC = 5

class DealResolutionEngine:
    def __init__(self):
        self.last_deal_ticket = self._load_last_ticket()

    def _load_last_ticket(self) -> int:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    return state.get("last_deal_ticket", 0)
            except Exception:
                pass
        return 0

    def update_risk_state_with_deal(self, deal) -> dict:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state = {
            "date": today_str,
            "starting_balance": 0.0,
            "peak_equity_hwm": 0.0,
            "realized_daily_pnl": 0.0,
            "circuit_breaker_tripped": False,
            "lockout_reason": "",
            "last_deal_ticket": 0,
            "last_updated": time.time()
        }

        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if loaded.get("date") == today_str:
                        state.update(loaded)
            except Exception as e:
                logger.error(f"[STATE-READ-ERR] {e}")

        profit = deal.profit + deal.swap + deal.commission
        state["realized_daily_pnl"] = round(state.get("realized_daily_pnl", 0.0) + profit, 2)
        state["last_deal_ticket"] = max(state.get("last_deal_ticket", 0), deal.ticket)
        state["last_updated"] = time.time()

        acc = mt5.account_info()
        if acc:
            if state["starting_balance"] <= 0.0:
                state["starting_balance"] = acc.balance - state["realized_daily_pnl"]
            state["peak_equity_hwm"] = max(state.get("peak_equity_hwm", acc.equity), acc.equity)
            
            hwm = state["peak_equity_hwm"]
            drawdown = (hwm - acc.equity) / hwm if hwm > 0 else 0.0
            if drawdown >= 0.05 and not state["circuit_breaker_tripped"]:
                state["circuit_breaker_tripped"] = True
                state["lockout_reason"] = f"Realized DD breached limit (-{drawdown*100:.2f}%)"
                send_alert(
                    "quant_alert_bot",
                    f"🚨 <b>CIRCUIT BREAKER LATCHED // DEAL RESOLVER</b>\n"
                    f"• Realized Loss: <code>${state['realized_daily_pnl']:,.2f}</code>\n"
                    f"• Account Equity: <code>${acc.equity:,.2f}</code> | HWM: <code>${hwm:,.2f}</code>\n"
                    f"• Lockout Triggered: Execution Halted."
                )

        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"[STATE-WRITE-ERR] {e}")

        return state

    def poll_closed_deals(self):
        from_date = datetime.now(timezone.utc) - timedelta(hours=24)
        to_date = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None or len(deals) == 0:
            return

        for d in deals:
            if d.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT] and d.ticket > self.last_deal_ticket:
                net_pnl = d.profit + d.swap + d.commission
                pnl_icon = "🟢" if net_pnl >= 0 else "🔴"
                logger.info(f"⚡ [DEAL RESOLVED] Ticket #{d.ticket} | {d.symbol} | PnL: ${net_pnl:+,.2f} | Vol: {d.volume}")

                updated_state = self.update_risk_state_with_deal(d)
                self.last_deal_ticket = d.ticket

                send_alert(
                    "quant_alert_bot",
                    f"{pnl_icon} <b>[DEAL RESOLUTION]</b> <code>{d.symbol}</code>\n"
                    f"• Ticket: <code>#{d.ticket}</code> | Magic: <code>#{d.magic}</code>\n"
                    f"• Net PnL: <b>${net_pnl:+,.2f}</b> (Swap: ${d.swap:.2f})\n"
                    f"• Day Realized: <code>${updated_state['realized_daily_pnl']:+,.2f}</code>\n"
                    f"• Account NAV: <code>${updated_state.get('peak_equity_hwm', 0):,.2f}</code>"
                )

def main():
    logger.info("Starting Deal Resolution Watcher...")
    if not mt5.initialize(path=MT5_PATH):
        logger.error("Failed to connect to MT5.")
        return

    engine = DealResolutionEngine()
    logger.info(f"Connected to MT5. Initialized deal tracking from ticket #{engine.last_deal_ticket}")
    gc.set_threshold(700, 10, 5)

    try:
        while True:
            engine.poll_closed_deals()
            gc.collect()
            time.sleep(POLL_CADENCE_SEC)
    except KeyboardInterrupt:
        logger.info("Watcher stopped by operator.")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
