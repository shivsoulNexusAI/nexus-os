# =====================================================================
# SHIVSOUL NEXUS v7.0 // VOLATILITY-TARGETING POSITION SIZER (vol_target_sizer.py)
# =====================================================================
import MetaTrader5 as mt5
import numpy as np
import pandas as pd

class VolatilityTargetingSizer:
    def __init__(self, target_annual_vol: float = 0.15, default_capital: float = 1000.0):
        self.target_annual_vol = target_annual_vol
        self.default_capital = default_capital

    def compute_realized_vol(self, rates, window: int = 20) -> float:
        df = pd.DataFrame(rates)
        if df.empty or len(df) < window:
            return 0.05

        high = df['high'].tail(window)
        low = df['low'].tail(window)
        open_p = df['open'].tail(window)
        close = df['close'].tail(window)

        log_hl = (high / low).apply(np.log) ** 2
        log_co = (close / open_p).apply(np.log) ** 2
        
        gk_daily = np.sqrt(0.5 * log_hl - (2 * np.log(2) - 1) * log_co).mean()
        annualized_vol = gk_daily * np.sqrt(252)
        return max(annualized_vol, 0.01)

    def calculate_lot_size(self, symbol: str, risk_fraction: float = 0.01) -> dict:
        if not mt5.terminal_info():
            return {"error": "MT5 not initialized", "lots": 0.0}

        acc = mt5.account_info()
        equity = acc.equity if acc is not None else self.default_capital

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {"error": f"Symbol {symbol} not found in terminal", "lots": 0.0}

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
        if rates is None or len(rates) == 0:
            return {"error": "Failed to fetch rates for vol calculation", "lots": 0.0}

        realized_vol = self.compute_realized_vol(rates)
        vol_scalar = self.target_annual_vol / realized_vol
        vol_scalar = np.clip(vol_scalar, 0.2, 3.0)

        target_risk_amount = equity * risk_fraction * vol_scalar
        contract_size = symbol_info.trade_contract_size
        current_price = symbol_info.bid
        stop_loss_distance = current_price * 0.015 
        
        risk_per_lot = stop_loss_distance * contract_size
        if risk_per_lot <= 0:
            return {"error": "Invalid risk per lot calculation", "lots": 0.0}

        raw_lots = target_risk_amount / risk_per_lot
        lot_step = symbol_info.volume_step
        min_lot = symbol_info.volume_min
        max_lot = symbol_info.volume_max

        normalized_lots = round(round(raw_lots / lot_step) * lot_step, 2)
        final_lots = max(min(normalized_lots, max_lot), min_lot)

        return {
            "symbol": symbol,
            "equity": equity,
            "realized_vol": round(realized_vol, 4),
            "vol_scalar": round(vol_scalar, 2),
            "recommended_lots": final_lots
        }

if __name__ == "__main__":
    from nexus_ship_core import SLEEVES
    cfg = SLEEVES["T1"]
    if mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"]):
        sizer = VolatilityTargetingSizer(target_annual_vol=0.15)
        res = sizer.calculate_lot_size("BTCUSD")
        print("=== VOLATILITY-TARGETING SIZER AUDIT ===")
        print(res)
        mt5.shutdown()
