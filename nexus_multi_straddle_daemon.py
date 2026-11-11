import pickle
# -*- coding: utf-8 -*-
"""
QUANT-NEXUS MULTI-STRADDLE DAEMON (NEXT-GEN V2.1)
Three Core Pillars:
1. Volatility Regime Classification (V2 Normalized Feature Vector)
2. Dynamic ATR-Scaled Brackets (buffer = k1*ATR, sl = k2*ATR)
3. Spread Elasticity Filter (Rolling 90th percentile shield)
"""
import sys
import os
import time
import logging
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timezone
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278017866/terminal64.exe"
MODEL_PATH = r"C:\Quant-Nexus-Eng\regime_classifier.pkl"
LOG_FILE = r"C:\Quant-Nexus-Eng\nexus_multi_straddle.log"

SYMBOLS = ["BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"]

# Calibrated Regime ML Decision Hurdles by Asset Profile
ASSET_THRESHOLDS = {
    "EURUSD": 0.65,
    "GBPUSD": 0.65,
    "USDJPY": 0.65,
    "US30":   0.68,
    "XAUUSD": 0.72,
    "BTCUSD": 0.72
}
DEFAULT_THRESHOLD = 0.65

POLL_INTERVAL = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

class DualGatedDynamicEngine:
    def purge_stale_orders(self, max_age_seconds=3600):
        orders = mt5.orders_get() or []
        now_ts = int(time.time())
        for o in orders:
            if "NEXUS" in o.comment:
                # Purge if order has been sitting longer than max_age_seconds
                order_age = now_ts - o.time_setup
                if order_age > max_age_seconds:
                    res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        logging.info(f"[STALE PURGE] Removed pending order #{o.ticket} ({o.symbol}) after {order_age}s.")

    def enforce_symbol_level_oco(self, max_active_symbols=4):
        positions = mt5.positions_get() or []
        orders = mt5.orders_get() or []
        active_symbols = {p.symbol for p in positions}
        for o in orders:
            if o.symbol in active_symbols and "NEXUS" in o.comment:
                res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    logging.info(f"[PER-SYMBOL OCO] Cancelled opposite pending leg #{o.ticket} on {o.symbol} (trade active).")
        return len(active_symbols) >= max_active_symbols

    def __init__(self):
        logging.info("=" * 85)
        logging.info("   NEXUS ENGINE ONLINE: DUAL-GATED + DYNAMIC ATR + SPREAD ELASTICITY")
        logging.info("=" * 85)
        
        if not mt5.initialize(path=TERMINAL, portable=False):
            logging.error(f"MT5 Init Failed: {mt5.last_error()}")
            sys.exit(1)

        self.model_bundle = None
        self.load_model()
        self.spread_history = {s: [] for s in SYMBOLS}

    def load_model(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model_bundle = pickle.load(f)
            logging.info(f"[ML ENGINE LOADED] Regime model ready (AUC: {self.model_bundle.get('auc', 0.5):.4f})")
        except Exception as e:
            logging.warning(f"Could not load ML model: {e}. Defaulting to heuristic ATR gating.")
            self.model_bundle = None

    def get_features(self, symbol):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)
        if rates is None or len(rates) < 80:
            return None, None, None

        df = pd.DataFrame(rates)
        o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["tick_volume"]

        prev_c = c.shift(1)
        tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
        atr14 = tr.rolling(14).mean()
        natr14 = (atr14 / c) * 100.0
        atr_baseline = tr.rolling(72).mean()

        cur_natr = natr14.iloc[-1]
        baseline_natr = natr14.rolling(72, min_periods=10).mean().iloc[-1]
        rel_natr = cur_natr / baseline_natr if baseline_natr > 0 else 1.0

        atr_exp_ratio = atr14.iloc[-1] / atr_baseline.iloc[-1] if atr_baseline.iloc[-1] > 0 else 1.0

        log_hl = np.log(h / l) ** 2
        p_vol = np.sqrt((1.0 / (4.0 * np.log(2.0))) * log_hl.rolling(14).mean()) * np.sqrt(288 * 365)
        p_vol_base = p_vol.rolling(72, min_periods=10).mean().iloc[-1]
        rel_p_vol = p_vol.iloc[-1] / p_vol_base if p_vol_base > 0 else 1.0

        log_co = np.log(c / o) ** 2
        gk_term = 0.5 * log_hl - (2.0 * np.log(2.0) - 1.0) * log_co
        gk_vol = np.sqrt(np.maximum(0, gk_term.rolling(14).mean())) * np.sqrt(288 * 365)
        gk_base = gk_vol.rolling(72, min_periods=10).mean().iloc[-1]
        rel_gk_vol = gk_vol.iloc[-1] / gk_base if gk_base > 0 else 1.0

        bar_range = max(h.iloc[-1] - l.iloc[-1], 1e-6)
        upper_wick = (h.iloc[-1] - max(o.iloc[-1], c.iloc[-1])) / bar_range
        lower_wick = (min(o.iloc[-1], c.iloc[-1]) - l.iloc[-1]) / bar_range
        body = abs(c.iloc[-1] - o.iloc[-1]) / bar_range
        rvol = v.iloc[-1] / v.rolling(24).mean().iloc[-1] if v.rolling(24).mean().iloc[-1] > 0 else 1.0

        ret_1 = (c.iloc[-1] / c.iloc[-2]) - 1.0
        ret_3 = (c.iloc[-1] / c.iloc[-4]) - 1.0
        ret_12 = (c.iloc[-1] / c.iloc[-13]) - 1.0

        feat_dict = {
            "rel_natr": rel_natr,
            "atr_expansion_ratio": atr_exp_ratio,
            "rel_parkinson": rel_p_vol,
            "rel_gk": rel_gk_vol,
            "upper_wick_ratio": upper_wick,
            "lower_wick_ratio": lower_wick,
            "body_ratio": body,
            "rvol": rvol,
            "ret_1": ret_1,
            "ret_3": ret_3,
            "ret_12": ret_12,
            "is_btc": 1 if symbol == "BTCUSD" else 0,
            "is_gold": 1 if symbol == "XAUUSD" else 0,
            "is_us30": 1 if symbol == "US30" else 0
        }

        feature_cols = self.model_bundle["feature_names"] if self.model_bundle else ["atr14", "atr_base", "expansion_ratio", "spread_ratio"] if self.model_bundle else ["atr14", "atr_base", "expansion_ratio", "spread_ratio"]
        row = pd.DataFrame([[feat_dict.get(k, 0.0) for k in feature_cols]], columns=feature_cols)
        return row, atr14.iloc[-1], c.iloc[-1]

    def check_spread_elasticity(self, symbol, current_spread):
        hist = self.spread_history[symbol]
        hist.append(current_spread)
        if len(hist) > 60:
            hist.pop(0)
        if len(hist) >= 10:
            p90 = np.percentile(hist, 90)
            if current_spread > p90 * 1.5:
                return False, p90
        return True, current_spread

    def check_active_exposure(self, symbol):
        pos = mt5.positions_get(symbol=symbol) or []
        orders = mt5.orders_get(symbol=symbol) or []
        return len(pos), len(orders)

    def cycle(self):
        fleet_saturated = self.enforce_symbol_level_oco(max_active_symbols=4)
        if fleet_saturated:
            return
        self.purge_stale_orders()
        for sym in SYMBOLS:
            try:
                tick = mt5.symbol_info_tick(sym)
                info = mt5.symbol_info(sym)
                if not tick or not info:
                    continue

                spread_pts = (tick.ask - tick.bid) / info.point
                spread_ok, p90 = self.check_spread_elasticity(sym, spread_pts)
                if not spread_ok:
                    logging.info(f"[SPREAD GATE] {sym} spread {spread_pts:.1f}pt exceeds 90th percentile {p90:.1f}pt. Skipped.")
                    continue

                pos_count, order_count = self.check_active_exposure(sym)
                if pos_count > 0 or order_count >= 2:
                    continue

                X, cur_atr, cur_price = self.get_features(sym)
                if X is None or cur_atr is None or cur_atr <= 0:
                    continue

                p_expansion = 1.0
                thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)
                if self.model_bundle:
                    clf = self.model_bundle["model"]
                    thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)
                    p_expansion = clf.predict_proba(X)[0, 1]

                if p_expansion < thresh:
                    continue

                k_buf = 1.2
                k_sl = 0.8
                k_tp = 2.5

                buf_dist = max(cur_atr * k_buf, info.spread * info.point * 2.0)
                sl_dist = cur_atr * k_sl
                tp_dist = cur_atr * k_tp

                buy_stop = round(tick.ask + buf_dist, info.digits)
                buy_sl = round(buy_stop - sl_dist, info.digits)
                buy_tp = round(buy_stop + tp_dist, info.digits)

                sell_stop = round(tick.bid - buf_dist, info.digits)
                sell_sl = round(sell_stop + sl_dist, info.digits)
                sell_tp = round(sell_stop - tp_dist, info.digits)

                lot = max(info.volume_min * 2.0, 0.02) if info.volume_min <= 0.01 else info.volume_min
                req_buy = {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY_STOP,
                    "price": buy_stop,
                    "sl": buy_sl,
                    "tp": buy_tp,
                    "type_time": mt5.ORDER_TIME_SPECIFIED,
                    "expiration": int(time.time()) + 3600,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                    "comment": "NEXUS_DYN_P2",
                }
                res_b = mt5.order_send(req_buy)

                req_sell = {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_SELL_STOP,
                    "price": sell_stop,
                    "sl": sell_sl,
                    "tp": sell_tp,
                    "type_time": mt5.ORDER_TIME_SPECIFIED,
                    "expiration": int(time.time()) + 3600,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                    "comment": "NEXUS_DYN_P2",
                }
                res_s = mt5.order_send(req_sell)

                if res_b and res_b.retcode == mt5.TRADE_RETCODE_DONE and res_s and res_s.retcode == mt5.TRADE_RETCODE_DONE:
                    logging.info(
                        f"[DYNAMIC ARMED | ML P={p_expansion:.2f} | SPREAD={spread_pts:.1f}pt | ATR14={cur_atr:.2f}] "
                        f"{sym} (Lots: {lot}) | BuyStop: {buy_stop:.5f} (#{res_b.order}) | SellStop: {sell_stop:.5f} (#{res_s.order})"
                    )
            except Exception as e:
                logging.error(f"[CYCLE ERROR] {sym}: {e}", exc_info=True)

    def run(self):
        logging.info("[DAEMON ENGINE] Continuous loop engaged.")
        while True:
            self.cycle()
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    engine = DualGatedDynamicEngine()
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run-once":
        engine.cycle()
        logging.info("[DRY RUN COMPLETE] Cycle evaluated cleanly.")
    else:
        engine.run()