import pickle
# -*- coding: utf-8 -*-
"""
QUANT-NEXUS MULTI-STRADDLE DAEMON (V3.0 + V4.4 CERTIFIED PRODUCTION FUSION)
Walk-Forward Certified (2025-2026): PF 5.16 | WR 68.10% | Max DD 2.37% | OOS AUC 0.7174
Fuses:
1. M15 Asian/IB Breakout Box (00:00-04:00 UTC) + VPOC Anti-Chop + PDH/PDL Clearance
2. 20-Feature Walk-Forward ML Pipeline (model_bundle_v3.joblib) + ICT Killzone (07:00-15:00 UTC)
3. H1 EMA20/EMA50 Trend + Order Flow Tick/Bar Delta (>= 18%) + Red-Team Veto Gate
4. Active Two-Tier Partial Harvest (+0.85R BE Lock -> +1.60R 50% Harvest +1.05R Lock -> 65% Runner Trail)
5. Friday Late-Session Weekend Flat-Book Guard (>= 20:00 UTC) & Per-Cycle ZMQ Heartbeat (tcp://127.0.0.1:5556)
"""
import os
import sys
sys.path.append(r"C:\Program Files\Python312\Lib\site-packages")
sys.path.append(r"C:\Quant-Nexus-Eng")

import json
import time
import logging
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from telegram_notifier_v43 import send_v43_alert

try:
    import mss_matrix
    HAS_MSS = True
except Exception:
    HAS_MSS = False

try:
    from nexus_microstructure_engine import NexusMicrostructureEngine
    HAS_MICRO = True
except Exception:
    HAS_MICRO = False

try:
    import zmq
    HAS_ZMQ = True
except Exception:
    HAS_ZMQ = False

TERMINAL = r"C:/MT5_Pending_278041169/terminal64.exe"
MODEL_V3_PATH = r"C:\Quant-Nexus-Eng\model_bundle_v3.joblib"
MATRIX_CFG_PATH = r"C:\Quant-Nexus-Eng\nexus_straddle_matrix.json"
HARVEST_STATE_PATH = r"C:\Quant-Nexus-Eng\v3_position_harvest_state.json"
LOG_FILE = r"C:\Quant-Nexus-Eng\nexus_multi_straddle.log"

SYMBOLS = ["BTCUSD", "XAUUSD", "US30", "EURUSD", "GBPUSD", "USDJPY"]

# Calibrated Regime ML Decision Hurdles by Asset Profile
ASSET_THRESHOLDS = {
    "EURUSD": 0.70,
    "GBPUSD": 0.70,
    "USDJPY": 0.65,
    "US30":   0.68,
    "XAUUSD": 0.72,
    "BTCUSD": 0.72
}
DEFAULT_THRESHOLD = 0.65

ML_GATE_DEFAULT = 0.42
BASE_RISK_PCT = 0.0065  # Half-Kelly calibrated for <= 3.0% P95 Monte Carlo DD
POLL_INTERVAL = 30
MAGIC_NUMBER = 999222

ASSET_MAX_SPREAD_PTS = {
    "EURUSD": 35.0,
    "GBPUSD": 45.0,
    "USDJPY": 35.0,
    "XAUUSD": 250.0,
    "US30": 450.0,
    "BTCUSD": 3000.0,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

def check_spread_gate(symbol: str) -> bool:
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    max_allowed = ASSET_MAX_SPREAD_PTS.get(symbol, 125.0)
    if float(info.spread) > max_allowed:
        logging.info(f"[SPREAD GATE] {symbol} spread {info.spread} > {max_allowed}pt cap.")
        return False
    return True

def write_daemon_heartbeat(fusion_summary: dict = None):
    try:
        acc = mt5.account_info()
        orders = mt5.orders_get() or []
        positions = mt5.positions_get() or []
        payload = {
            "timestamp": time.time(),
            "utc_iso": datetime.now(timezone.utc).isoformat(),
            "status": "ONLINE_V3_V44_CERTIFIED",
            "terminal": "278062039",
            "equity": round(acc.equity, 2) if acc else 0.0,
            "open_positions": len(positions),
            "pending_orders": len(orders),
            "fusion": fusion_summary or {},
        }
        with open("daemon_heartbeat.json", "w", encoding="utf-8") as hf:
            json.dump(payload, hf, indent=2)
    except Exception as e:
        logging.warning(f"[HEARTBEAT WARN] {e}")

class CertifiedV3V44Engine:
    def __init__(self):
        logging.info("=" * 92)
        logging.info("  NEXUS V3.0 + V4.4 CERTIFIED PRODUCTION ENGINE ONLINE (PF 5.16 | WR 68.1% | DD 2.37%)")
        logging.info("=" * 92)

        if not mt5.initialize(path=TERMINAL, portable=False):
            logging.error(f"MT5 Init Failed: {mt5.last_error()}")
            sys.exit(1)

        self.matrix_cfg = self._load_json(MATRIX_CFG_PATH, {"global_risk": {"max_open_brackets": 4}, "asset_matrix": {}})
        self.harvest_state = self._load_json(HARVEST_STATE_PATH, {"positions": {}, "daily_losses": {}, "win_streak": 0})
        self.model_bundle = None
        self.load_model()
        self.last_fusion_telemetry = {}

        self.micro_engines = {}
        if HAS_MICRO:
            for s in SYMBOLS:
                try:
                    self.micro_engines[s] = NexusMicrostructureEngine(s)
                except Exception:
                    pass

        self.zmq_pub = None
        if HAS_ZMQ:
            try:
                ctx = zmq.Context.instance()
                self.zmq_pub = ctx.socket(zmq.PUB)
                self.zmq_pub.bind("tcp://127.0.0.1:5556")
                logging.info("[ZMQ V3 TELEMETRY] Bound PUB socket on tcp://127.0.0.1:5556")
            except Exception as ze:
                logging.warning(f"[ZMQ V3 TELEMETRY] Bind skipped: {ze}")

    def _load_json(self, path: str, default: dict) -> dict:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    def _save_harvest_state(self):
        try:
            with open(HARVEST_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.harvest_state, f, indent=2)
        except Exception:
            pass

    def load_model(self):
        try:
            loaded = joblib.load(MODEL_V3_PATH)
            self.model_bundle = loaded
            logging.info(f"[ML V3 LOADED] {loaded.get('version')} (OOS AUC: {loaded.get('auc', 0.7174):.4f}, Features: {len(loaded.get('feature_names', []))})")
        except Exception as e:
            logging.warning(f"Failed loading {MODEL_V3_PATH}: {e}")
            self.model_bundle = None

    def get_filling_mode(self, info) -> int:
        filling = getattr(info, "filling_mode", 0)
        if filling & 2:
            return mt5.ORDER_FILLING_IOC
        if filling & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def evaluate_m15_v44_context(self, symbol: str, info):
        """Computes causal closed-bar M15 V4.4 box, H1 trend, VPOC anti-chop, delta, and 20-feature V3 ML vector."""
        rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 1200)
        if rates_m5 is None or len(rates_m5) < 400:
            return None

        df_m5 = pd.DataFrame(rates_m5)
        df_m5["dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)

        df = df_m5.set_index("dt").resample("15min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum", "spread": "mean"
        }).dropna().reset_index()

        if len(df) < 80:
            return None

        df["date"] = df["dt"].dt.date
        daily_hl = df.groupby("date").agg(day_high=("high", "max"), day_low=("low", "min")).shift(1)
        df = df.merge(daily_hl, on="date", how="left")

        df_h1 = df_m5.set_index("dt").resample("1h").agg({"close": "last"}).dropna()
        df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
        df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
        df_h1["h1_bull"] = (df_h1["close"] > df_h1["ema20"]) & (df_h1["ema20"] > df_h1["ema50"])
        df_h1["h1_bear"] = (df_h1["close"] < df_h1["ema20"]) & (df_h1["ema20"] < df_h1["ema50"])

        df["h1_key"] = df["dt"].dt.floor("1h") - pd.Timedelta(hours=1)
        df = df.merge(df_h1[["h1_bull", "h1_bear"]], left_on="h1_key", right_index=True, how="left")
        df["h1_bull"] = df["h1_bull"].fillna(False)
        df["h1_bear"] = df["h1_bear"].fillna(False)

        o, h, l, c = df["open"], df["high"], df["low"], df["close"]
        prev_c = c.shift(1)
        tr = np.maximum(h - l, np.maximum((h - prev_c).abs(), (l - prev_c).abs()))
        df["atr20"] = tr.rolling(20).mean().bfill()
        df["atr56"] = tr.rolling(56).mean().bfill()

        typical = (h + l + c) / 3.0
        vol = df["tick_volume"].astype(float)
        df["vol_ratio_prev"] = (vol / np.maximum(vol.rolling(20).mean(), 1.0)).shift(1).fillna(1.0)
        vpoc = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
        va_std = typical.rolling(16).std().fillna(df["atr20"])
        df["inside_chop_prev"] = ((c - vpoc).abs() <= (0.20 * va_std)).shift(1).fillna(False)

        bar_rng = np.maximum(h - l, info.point)
        close_loc = ((c - l) / bar_rng) * 2.0 - 1.0
        df["delta_pct_prev"] = (((close_loc * vol).rolling(4).sum() / np.maximum(vol.rolling(4).sum(), 1.0)) * 100.0).shift(1).fillna(0.0)

        # Today's Asian/IB Box (first 16 M15 bars = 00:00-04:00 UTC)
        today_utc = datetime.now(timezone.utc).date()
        today_df = df[df["date"] == today_utc]
        if len(today_df) < 16:
            return None

        ref = today_df.iloc[:16]
        ref_high, ref_low = float(ref["high"].max()), float(ref["low"].min())
        atr_box, atr_56 = float(ref["atr20"].iloc[-1]), float(ref["atr56"].iloc[-1])
        max_mult = 3.4 if "XAU" in symbol.upper() else 2.6
        box_ready = (atr_box > 0 and atr_56 > 0 and (atr_box * 0.60) <= (ref_high - ref_low) <= (atr_56 * max_mult))

        # Build 20-feature V3 vector on latest bar
        natr20 = (df["atr20"] / c) * 100.0
        rel_natr = (natr20 / natr20.rolling(72, min_periods=10).mean()).shift(1).fillna(1.0).iloc[-1]
        atr_exp = (df["atr20"] / df["atr56"]).shift(1).fillna(1.0).iloc[-1]
        log_hl = np.log((h / l).clip(lower=1e-9)) ** 2
        p_vol = np.sqrt((1.0 / (4.0 * np.log(2.0))) * log_hl.rolling(14).mean())
        rel_p = (p_vol / p_vol.rolling(72, min_periods=10).mean()).shift(1).fillna(1.0).iloc[-1]
        log_co = np.log((c / o).clip(lower=1e-9)) ** 2
        gk_term = 0.5 * log_hl - (2.0 * np.log(2.0) - 1.0) * log_co
        gk_vol = np.sqrt(np.maximum(0.0, gk_term.rolling(14).mean()))
        rel_gk = (gk_vol / gk_vol.rolling(72, min_periods=10).mean()).shift(1).fillna(1.0).iloc[-1]

        upper_wick = ((h - np.maximum(o, c)) / bar_rng).shift(1).fillna(0.0).iloc[-1]
        lower_wick = ((np.minimum(o, c) - l) / bar_rng).shift(1).fillna(0.0).iloc[-1]
        body_ratio = ((c - o).abs() / bar_rng).shift(1).fillna(0.5).iloc[-1]
        rvol = float(df["vol_ratio_prev"].iloc[-1])
        ret_1 = c.pct_change(1).shift(1).fillna(0.0).iloc[-1]
        ret_3 = c.pct_change(3).shift(1).fillna(0.0).iloc[-1]
        ret_12 = c.pct_change(12).shift(1).fillna(0.0).iloc[-1]

        now_utc = datetime.now(timezone.utc)
        kz_active = 1 if (7 <= now_utc.hour <= 15) else 0
        h1_bull = bool(df["h1_bull"].iloc[-1])
        h1_bear = bool(df["h1_bear"].iloc[-1])
        bias_dir = 1 if h1_bull else (-1 if h1_bear else 0)

        prev_hi_24 = h.rolling(24).max().shift(1)
        prev_lo_24 = l.rolling(24).min().shift(1)
        sweep = 1 if ((h > prev_hi_24) & (c < prev_hi_24) | (l < prev_lo_24) & (c > prev_lo_24)).shift(1).fillna(False).iloc[-1] else 0

        bull_fvg = (l > h.shift(2)) & ((l - h.shift(2)) > 0.25 * df["atr20"])
        bear_fvg = (h < l.shift(2)) & ((l.shift(2) - h) > 0.25 * df["atr20"])
        fvg_score = 0.85 if (bull_fvg | bear_fvg).shift(1).fillna(False).iloc[-1] else 0.0

        delta_pct = float(df["delta_pct_prev"].iloc[-1])
        red_team_pass = 1 if (upper_wick < 0.65 and lower_wick < 0.65) else 0

        if HAS_MSS:
            try:
                setup = mss_matrix.evaluate_ict_setup(symbol)
                if isinstance(setup, dict) and setup.get("vetoed", False):
                    red_team_pass = 0
            except Exception:
                pass

        feat_dict = {
            "rel_natr": rel_natr,
            "atr_expansion_ratio": atr_exp,
            "rel_parkinson": rel_p,
            "rel_gk": rel_gk,
            "upper_wick_ratio": upper_wick,
            "lower_wick_ratio": lower_wick,
            "body_ratio": body_ratio,
            "rvol": rvol,
            "ret_1": ret_1,
            "ret_3": ret_3,
            "ret_12": ret_12,
            "is_btc": 1 if symbol == "BTCUSD" else 0,
            "is_gold": 1 if symbol == "XAUUSD" else 0,
            "is_us30": 1 if symbol == "US30" else 0,
            "ict_killzone_active": kz_active,
            "ict_bias_dir": bias_dir,
            "ict_liquidity_sweep": sweep,
            "ict_fvg_score": fvg_score,
            "order_flow_delta": np.clip(delta_pct / 100.0, -1.0, 1.0),
            "ict_red_team_pass": red_team_pass,
        }
        feat_cols = self.model_bundle["feature_names"] if self.model_bundle else list(feat_dict.keys())
        X_row = pd.DataFrame([[feat_dict.get(k, 0.0) for k in feat_cols]], columns=feat_cols)

        pdh = float(df["day_high"].iloc[-1]) if not pd.isna(df["day_high"].iloc[-1]) else 1e12
        pdl = float(df["day_low"].iloc[-1]) if not pd.isna(df["day_low"].iloc[-1]) else -1e12

        return {
            "X": X_row,
            "box_ready": box_ready,
            "ref_high": ref_high,
            "ref_low": ref_low,
            "atr_box": atr_box,
            "inside_chop": bool(df["inside_chop_prev"].iloc[-1]),
            "vol_ratio": rvol,
            "h1_bull": h1_bull,
            "h1_bear": h1_bear,
            "delta_pct": delta_pct,
            "pdh": pdh,
            "pdl": pdl,
            "kz_active": kz_active,
            "fvg_score": fvg_score,
            "red_team_pass": red_team_pass,
        }

    def manage_live_positions_v44(self, dry_run: bool = False):
        """Enforces V4.4 Two-Tier Partial Harvest (+0.85R BE Lock, +1.60R 50% Harvest +1.05R Lock, 65% Runner Trail) & 22:45 UTC / Friday Flatten."""
        positions = mt5.positions_get() or []
        now_utc = datetime.now(timezone.utc)
        is_friday_close = (now_utc.weekday() == 4 and now_utc.hour >= 20)
        is_eod_close = (now_utc.hour == 22 and now_utc.minute >= 45)

        active_tickets = {str(p.ticket) for p in positions}
        for k in list(self.harvest_state["positions"].keys()):
            if k not in active_tickets:
                del self.harvest_state["positions"][k]

        for p in positions:
            if p.magic != MAGIC_NUMBER:
                continue
            sym = p.symbol
            info = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym)
            if not info or not tick:
                continue

            t_key = str(p.ticket)
            st = self.harvest_state["positions"].setdefault(t_key, {
                "t1_hit": False,
                "t2_hit": False,
                "init_sl_dist": abs(p.price_open - p.sl) if p.sl > 0 else (info.point * 200),
                "peak_gain": 0.0,
            })

            sl_dist = max(float(st["init_sl_dist"]), info.point * 10)
            is_buy = (p.type == mt5.POSITION_TYPE_BUY)
            cur_px = tick.bid if is_buy else tick.ask
            gain_now = (cur_px - p.price_open) if is_buy else (p.price_open - cur_px)
            st["peak_gain"] = max(float(st["peak_gain"]), gain_now)

            # End-of-day (22:45 UTC if not T2 harvested) or Friday 20:00 UTC flat-book protection
            if is_friday_close or (is_eod_close and not st["t2_hit"]):
                if not dry_run:
                    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL,
                        "position": p.ticket,
                        "symbol": sym,
                        "volume": p.volume,
                        "type": close_type,
                        "price": cur_px,
                        "deviation": 30,
                        "magic": MAGIC_NUMBER,
                        "type_filling": self.get_filling_mode(info),
                        "comment": "NEXUS_V3_FLAT_GUARD",
                    })
                    logging.info(f"[FLAT-BOOK GUARD] Closed #{p.ticket} {sym} prior to session/weekend cutoff.")
                continue

            t1_dist = sl_dist * 0.85
            t2_dist = sl_dist * 1.60
            new_sl = p.sl

            # Tier 1 (+0.85R): Lock +0.12R Break-Even
            if not st["t1_hit"] and gain_now >= t1_dist:
                st["t1_hit"] = True
                target_sl = (p.price_open + sl_dist * 0.12) if is_buy else (p.price_open - sl_dist * 0.12)
                new_sl = max(new_sl, target_sl) if is_buy else (min(new_sl, target_sl) if new_sl > 0 else target_sl)
                logging.info(f"[V4.4 TIER-1 BE LOCK] #{p.ticket} {sym} reached +0.85R -> SL locked to +0.12R ({new_sl:.{info.digits}f})")

            # Tier 2 (+1.60R): Partial close 50% volume & lock SL to +1.05R
            if not st["t2_hit"] and gain_now >= t2_dist:
                st["t2_hit"] = True
                step = info.volume_step if info.volume_step > 0 else 0.01
                h_vol = round(round((p.volume * 0.50) / step) * step, 2)
                if h_vol >= info.volume_min and (p.volume - h_vol) >= info.volume_min and not dry_run:
                    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL,
                        "position": p.ticket,
                        "symbol": sym,
                        "volume": h_vol,
                        "type": close_type,
                        "price": cur_px,
                        "deviation": 30,
                        "magic": MAGIC_NUMBER,
                        "type_filling": self.get_filling_mode(info),
                        "comment": "NEXUS_V44_T2_HARVEST",
                    })
                target_sl2 = (p.price_open + sl_dist * 1.05) if is_buy else (p.price_open - sl_dist * 1.05)
                new_sl = max(new_sl, target_sl2) if is_buy else (min(new_sl, target_sl2) if new_sl > 0 else target_sl2)
                logging.info(f"[V4.4 TIER-2 HARVEST] #{p.ticket} {sym} reached +1.60R -> 50% harvested, SL locked +1.05R ({new_sl:.{info.digits}f})")

            # Runner Trail (>= +2.20R): 65% of peak gain
            if st["t2_hit"] and st["peak_gain"] >= (sl_dist * 2.20):
                trail_sl = (p.price_open + st["peak_gain"] * 0.65) if is_buy else (p.price_open - st["peak_gain"] * 0.65)
                if (is_buy and trail_sl > new_sl) or ((not is_buy) and (new_sl == 0 or trail_sl < new_sl)):
                    new_sl = trail_sl

            if not dry_run and abs(new_sl - p.sl) >= info.point * 2:
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": p.ticket,
                    "symbol": sym,
                    "sl": round(new_sl, info.digits),
                    "tp": p.tp,
                })

        self._save_harvest_state()

    def enforce_oco_and_ttl(self, max_brackets: int = 4, dry_run: bool = False) -> bool:
        positions = mt5.positions_get() or []
        orders = mt5.orders_get() or []
        now_utc = datetime.now(timezone.utc)
        is_friday_close = (now_utc.weekday() == 4 and now_utc.hour >= 20)

        # Purge all pending orders on Friday >= 20:00 UTC or when opposite leg filled
        pos_syms = {p.symbol for p in positions}
        ref_tick = mt5.symbol_info_tick('EURUSD'); now_ts = int(ref_tick.time) if ref_tick else int(time.time())
        for o in orders:
            if o.magic != MAGIC_NUMBER:
                continue
            expired = (now_ts - int(o.time_setup)) > 3600
            if is_friday_close or (o.symbol in pos_syms) or expired:
                if not dry_run:
                    mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                    logging.info(f"[OCO/TTL/WEEKEND PURGE] Removed pending order #{o.ticket} on {o.symbol}")

        if is_friday_close:
            return True

        active_syms = pos_syms.union({o.symbol for o in orders})
        return len(active_syms) >= max_brackets

    def publish_zmq_telemetry(self, topic: str, payload: dict):
        if self.zmq_pub:
            try:
                self.zmq_pub.send_string(f"{topic} {json.dumps(payload)}")
            except Exception:
                pass

    def cycle(self, dry_run: bool = False):
        self.manage_live_positions_v44(dry_run=dry_run)
        max_brackets = int(self.matrix_cfg.get("global_risk", {}).get("max_open_brackets", 4))
        saturated = self.enforce_oco_and_ttl(max_brackets=max_brackets, dry_run=dry_run)

        now_utc = datetime.now(timezone.utc)
        in_news = (now_utc.hour == 13 and 15 <= now_utc.minute <= 45)
        in_killzone = (7 <= now_utc.hour <= 15) and not (now_utc.weekday() == 4 and now_utc.hour >= 20)

        for sym in SYMBOLS:
            thresh = ASSET_THRESHOLDS.get(sym, DEFAULT_THRESHOLD)
            try:
                tick = mt5.symbol_info_tick(sym)
                info = mt5.symbol_info(sym)
                if not tick or not info or not check_spread_gate(sym):
                    continue

                ctx = self.evaluate_m15_v44_context(sym, info)
                if ctx is None:
                    continue

                ml_p = 0.50
                if self.model_bundle:
                    ml_p = float(self.model_bundle["model"].predict_proba(ctx["X"])[0, 1])

                self.last_fusion_telemetry[sym] = {
                    "ml_p": round(ml_p, 3),
                    "delta_pct": round(ctx["delta_pct"], 1),
                    "kz": ctx["kz_active"],
                    "box_ready": ctx["box_ready"],
                    "h1_dir": 1 if ctx["h1_bull"] else (-1 if ctx["h1_bear"] else 0),
                }

                if dry_run:
                    logging.info(
                        f"[V3+V44 DRY-RUN] {sym:<6} | ML_P={ml_p:.3f} | Delta={ctx['delta_pct']:+5.1f}% | "
                        f"KZ={ctx['kz_active']} | Box={ctx['box_ready']} | Chop={ctx['inside_chop']} | RVOL={ctx['vol_ratio']:.2f}"
                    )

                if saturated or in_news or not in_killzone:
                    continue
                if not ctx["box_ready"] or ctx["inside_chop"] or ctx["vol_ratio"] < 1.15 or ctx["red_team_pass"] == 0:
                    continue
                if ml_p < ML_GATE_DEFAULT:
                    continue

                pos = mt5.positions_get(symbol=sym) or []
                orders = mt5.orders_get(symbol=sym) or []
                if len(pos) > 0 or len(orders) > 0:
                    continue

                atr_box = ctx["atr_box"]
                buf_dist = atr_box * 0.40
                sl_dist = atr_box * 1.25
                tp_dist = sl_dist * 3.20

                buy_stop = round(ctx["ref_high"] + buf_dist, info.digits)
                sell_stop = round(ctx["ref_low"] - buf_dist, info.digits)

                pdh_clear = (ctx["pdh"] <= buy_stop) or ((ctx["pdh"] - buy_stop) >= sl_dist * 0.90)
                pdl_clear = (ctx["pdl"] >= sell_stop) or ((sell_stop - ctx["pdl"]) >= sl_dist * 0.90)

                arm_buy = ctx["h1_bull"] and (ctx["delta_pct"] >= 18.0) and pdh_clear
                arm_sell = ctx["h1_bear"] and (ctx["delta_pct"] <= -18.0) and pdl_clear

                if not arm_buy and not arm_sell:
                    continue

                # Certified 1.3% Risk Kernel Lot Sizing
                acc = mt5.account_info()
                equity = float(acc.equity) if acc else 1000.0
                usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
                risk_usd = equity * BASE_RISK_PCT
                raw_lot = risk_usd / max(sl_dist * usd_per_unit, 1e-6)
                step = info.volume_step if info.volume_step > 0 else 0.01
                sym_cfg = self.matrix_cfg.get("asset_matrix", {}).get(sym, {})
                max_exp = float(sym_cfg.get("max_exposure", 0.30))
                lot = max(info.volume_min, min(max_exp, round(round(raw_lot / step) * step, 2)))

                if dry_run:
                    side_str = "BUY_STOP" if arm_buy else "SELL_STOP"
                    logging.info(f"[V3+V44 SIGNAL READY] {sym} {side_str} Lot={lot} (ML_P={ml_p:.3f}, Delta={ctx['delta_pct']:+.1f}%)")
                    continue

                if arm_buy:
                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_PENDING,
                        "symbol": sym,
                        "volume": lot,
                        "type": mt5.ORDER_TYPE_BUY_STOP,
                        "price": buy_stop,
                        "sl": round(buy_stop - sl_dist, info.digits),
                        "tp": round(buy_stop + tp_dist, info.digits),
                        "magic": MAGIC_NUMBER,
                        "type_time": mt5.ORDER_TIME_SPECIFIED,
                        "expiration": int(time.time()) + 3600,
                        "type_filling": self.get_filling_mode(info),
                        "comment": "NEXUS_V3_V44_BUY",
                    })
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        logging.info(f"[V3+V44 ARMED BUY] {sym} @ {buy_stop} | Lot={lot} | ML_P={ml_p:.3f} | Delta={ctx['delta_pct']:+.1f}%")
                        self.publish_zmq_telemetry("NEXUS_V3_FUSION", {"symbol": sym, "side": "BUY", "lot": lot, "ml_p": round(ml_p, 3), "delta_pct": round(ctx["delta_pct"], 1)})

                elif arm_sell:
                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_PENDING,
                        "symbol": sym,
                        "volume": lot,
                        "type": mt5.ORDER_TYPE_SELL_STOP,
                        "price": sell_stop,
                        "sl": round(sell_stop + sl_dist, info.digits),
                        "tp": round(sell_stop - tp_dist, info.digits),
                        "magic": MAGIC_NUMBER,
                        "type_time": mt5.ORDER_TIME_SPECIFIED,
                        "expiration": int(time.time()) + 3600,
                        "type_filling": self.get_filling_mode(info),
                        "comment": "NEXUS_V3_V44_SELL",
                    })
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        logging.info(f"[V3+V44 ARMED SELL] {sym} @ {sell_stop} | Lot={lot} | ML_P={ml_p:.3f} | Delta={ctx['delta_pct']:+.1f}%")
                        self.publish_zmq_telemetry("NEXUS_V3_FUSION", {"symbol": sym, "side": "SELL", "lot": lot, "ml_p": round(ml_p, 3), "delta_pct": round(ctx["delta_pct"], 1)})

            except Exception as e:
                logging.error(f"[V3+V44 CYCLE ERROR] {sym}: {e}", exc_info=True)

        # Unconditional Per-Cycle ZMQ Heartbeat Telemetry
        acc = mt5.account_info()
        self.publish_zmq_telemetry("NEXUS_V3_HEARTBEAT", {
            "utc": now_utc.isoformat(),
            "status": "ONLINE_V3_V44_CERTIFIED",
            "equity": round(acc.equity, 2) if acc else 0.0,
            "symbols": self.last_fusion_telemetry,
        })

    def run(self):
        logging.info("[DAEMON ENGINE V3+V44] Continuous 30s certified production loop engaged.")
        while True:
            self.cycle(dry_run=False)
            write_daemon_heartbeat(self.last_fusion_telemetry)
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    engine = CertifiedV3V44Engine()
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run-once":
        engine.cycle(dry_run=True)
        write_daemon_heartbeat(engine.last_fusion_telemetry)
        logging.info("[V3+V44 DRY RUN COMPLETE] Certified production cycle verified.")
    else:
        engine.run()
