import MetaTrader5 as mt5

class DynamicKellyEngine:
    def __init__(self, fraction_multiplier: float = 0.5, max_account_risk_pct: float = 2.5):
        self.fraction_multiplier = fraction_multiplier
        self.max_account_risk_pct = max_account_risk_pct

    def compute_position_size(
        self,
        symbol: str,
        setup_probability: float,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        account_equity: float,
        hard_max_lot: float
    ) -> float:
        p = setup_probability / 100.0 if setup_probability > 1.0 else setup_probability
        if p <= 0.50:
            return 0.01

        sl_dist = abs(entry_price - sl_price)
        tp_dist = abs(entry_price - tp_price)
        if sl_dist <= 0:
            return 0.01

        b = tp_dist / sl_dist
        q = 1.0 - p
        kelly_full = (p * b - q) / b
        if kelly_full <= 0:
            return 0.01

        f_star = kelly_full * self.fraction_multiplier
        risk_pct_limit = self.max_account_risk_pct / 100.0
        allocated_risk_pct = min(f_star, risk_pct_limit)
        risk_capital_usd = account_equity * allocated_risk_pct

        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return 0.01

        tick_value = sym_info.trade_tick_value
        tick_size = sym_info.trade_tick_size
        if tick_size <= 0 or tick_value <= 0:
            return 0.01

        risk_per_one_lot = (sl_dist / tick_size) * tick_value
        if risk_per_one_lot <= 0:
            return 0.01

        raw_lot = risk_capital_usd / risk_per_one_lot
        lot_step = sym_info.volume_step
        min_lot = sym_info.volume_min
        max_broker_lot = sym_info.volume_max

        steps = round(raw_lot / lot_step)
        sized_lot = steps * lot_step
        final_lot = max(min_lot, min(sized_lot, hard_max_lot, max_broker_lot))
        return round(final_lot, 2)

kelly_engine = DynamicKellyEngine(fraction_multiplier=0.5, max_account_risk_pct=2.5)
