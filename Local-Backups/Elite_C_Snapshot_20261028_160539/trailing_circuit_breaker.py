import os
import json
import logging
from datetime import datetime, timezone
import MetaTrader5 as mt5

logger = logging.getLogger("CircuitBreaker")
TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

class TrailingCircuitBreaker:
    def __init__(self, base_floor: float = 950.00, max_drawdown_pct: float = 0.05, state_file: str = "circuit_breaker_state.json"):
        self.base_floor = float(base_floor)
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.state_file = state_file
        self.hwm = self.base_floor / (1.0 - self.max_drawdown_pct)
        self.current_floor = self.base_floor
        self.is_tripped = False
        self.tripped_timestamp = None
        self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.hwm = max(data.get("high_water_mark", self.hwm), self.hwm)
                    self.current_floor = max(data.get("current_floor", self.base_floor), self.base_floor)
                    self.is_tripped = data.get("is_tripped", False)
                    self.tripped_timestamp = data.get("tripped_timestamp")
            except Exception as e:
                logger.error(f"[BREAKER] Failed to load state: {e}")

    def _save_state(self):
        data = {
            "high_water_mark": round(self.hwm, 2),
            "current_floor": round(self.current_floor, 2),
            "base_floor": round(self.base_floor, 2),
            "max_drawdown_pct": self.max_drawdown_pct,
            "is_tripped": self.is_tripped,
            "tripped_timestamp": self.tripped_timestamp,
            "last_updated_utc": datetime.now(timezone.utc).isoformat()
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"[BREAKER] Failed to save state: {e}")

    def evaluate(self, simulated_equity: float = None) -> dict:
        if self.is_tripped:
            return {"allowed": False, "reason": f"LATCHED since {self.tripped_timestamp}", "floor": self.current_floor, "hwm": self.hwm}

        if simulated_equity is not None:
            equity = float(simulated_equity)
        else:
            acc = mt5.account_info()
            if not acc:
                return {"allowed": False, "reason": "Failed to read MT5 account info", "floor": self.current_floor, "hwm": self.hwm}
            equity = acc.equity

        if equity > self.hwm:
            self.hwm = equity
            ratchet_floor = self.hwm * (1.0 - self.max_drawdown_pct)
            self.current_floor = max(self.base_floor, ratchet_floor)
            self._save_state()

        if equity <= self.current_floor:
            self.is_tripped = True
            self.tripped_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            self._save_state()
            if simulated_equity is None:
                self._emergency_purge()
            return {"allowed": False, "reason": f"Breach: Equity (${equity:.2f}) <= Floor (${self.current_floor:.2f})", "floor": self.current_floor, "hwm": self.hwm}

        buf = equity - self.current_floor
        return {"allowed": True, "reason": "OK", "equity": round(equity, 2), "floor": round(self.current_floor, 2), "hwm": round(self.hwm, 2), "buffer_usd": round(buf, 2), "buffer_pct": round((buf / equity) * 100, 2)}

    def _get_filling_mode(self, symbol: str) -> int:
        info = mt5.symbol_info(symbol)
        if not info:
            return mt5.ORDER_FILLING_IOC
        modes = info.filling_mode
        if modes & 1:
            return mt5.ORDER_FILLING_FOK
        elif modes & 2:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def _emergency_purge(self):
        positions = mt5.positions_get()
        if positions:
            for p in positions:
                tick = mt5.symbol_info_tick(p.symbol)
                if not tick:
                    continue
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
                filling = self._get_filling_mode(p.symbol)
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "type": close_type,
                    "price": price,
                    "deviation": 50,
                    "magic": 999888,
                    "type_filling": filling
                }
                mt5.order_send(req)
        orders = mt5.orders_get()
        if orders:
            for o in orders:
                mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})

    def reset_latch(self):
        self.is_tripped = False
        self.tripped_timestamp = None
        self._save_state()
