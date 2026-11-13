import socket
_T2_SINGLETON_SOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _T2_SINGLETON_SOCK.bind(("127.0.0.1", 47269))
except OSError:
    raise SystemExit(0)

import sys
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from telegram_notifier_v43 import send_v43_alert

sys.path.insert(0, r"C:\Quant-Nexus-OS")
try:
    from core.anti_whipsaw import AntiWhipsawEngine
except Exception:
    AntiWhipsawEngine = None

TERMINAL_PATH = r"C:/MT5_Pending_278041169/terminal64.exe"
TARGET_ACCOUNT = 278041169
MICRO_STATE_PATH = Path(r"C:\Quant-Nexus-Eng\microstructure_state.json")
STATE_PATH = Path(r"C:\Quant-Nexus-Eng\v44_runtime_state.json")
LOG_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)

CORE_TRIAD = ['XAUUSD', 'US30', 'BTCUSD', 'EURUSD', 'USDCHF', 'USDCAD']
COMPRESSION_MULT = {'XAUUSD': 3.4, 'US30': 2.6, 'BTCUSD': 2.6, 'EURUSD': 2.6, 'USDCHF': 2.6, 'USDCAD': 2.6}
BASE_RISK_PCT = 0.013
MAX_ACTIVE_ASSETS = 4
MAGIC_NUMBER = 20260440
LEGACY_MAGICS = {20260420, 20260430, MAGIC_NUMBER}


class QuantNexusV44Daemon:
    def __init__(self):
        self.whipsaw = AntiWhipsawEngine(cooldown_sec=900, max_consecutive_losses=2, penalty_sec=3600) if AntiWhipsawEngine else None
        self.processed_deals = set()
        self.daily_box_cache = {}
        self.daily_traded = set()
        self.win_streak = self._load_win_streak()

    def _load_win_streak(self) -> dict:
        try:
            if STATE_PATH.exists():
                return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("win_streak", {})
        except Exception:
            pass
        return {s: 0 for s in CORE_TRIAD}

    def _save_win_streak(self):
        try:
            STATE_PATH.write_text(json.dumps({"win_streak": self.win_streak, "updated_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def connect_mt5(self) -> bool:
        if mt5.initialize(path=TERMINAL_PATH, portable=True):
            ai = mt5.account_info()
            if ai and ai.login == TARGET_ACCOUNT:
                return True
            logging.error(f"Account mismatch: expected #{TARGET_ACCOUNT}, got #{getattr(ai, 'login', None)}")
            mt5.shutdown()
            return False
        if False:
            return True
        logging.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False

    def read_microstructure(self, sym: str) -> dict:
        try:
            ms_path = Path(r"C:/Quant-Nexus-Eng/microstructure_state.json")
            if ms_path.exists():
                raw = json.loads(ms_path.read_text(encoding="utf-8"))
                fleet = raw.get("fleet", {}) if isinstance(raw, dict) else {}
                if isinstance(fleet, dict) and sym in fleet and isinstance(fleet[sym], dict):
                    if "delta_pct" in fleet[sym]:
                        return fleet[sym]
        except Exception:
            pass

        # Self-contained exact V4.4 closed-bar M15 order-flow delta & VPOC chop calculation
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 1, 24)
        info = mt5.symbol_info(sym)
        if rates is None or len(rates) < 18 or not info:
            return {"delta_pct": 0.0, "inside_poc_chop": True}

        df = pd.DataFrame(rates)
        pt = info.point if info.point > 0 else 1e-5
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["tick_volume"].astype(float)

        vpoc = float((typical.iloc[-16:] * vol.iloc[-16:]).sum() / max(float(vol.iloc[-16:].sum()), 1.0))
        va_std = float(typical.iloc[-16:].std())
        if np.isnan(va_std) or va_std <= 0:
            va_std = float((df["high"] - df["low"]).iloc[-16:].mean())
        inside_chop = abs(float(df["close"].iloc[-1]) - vpoc) <= (0.20 * va_std)

        last4 = df.iloc[-4:]
        rng4 = np.maximum(last4["high"] - last4["low"], pt)
        cloc4 = ((last4["close"] - last4["low"]) / rng4) * 2.0 - 1.0
        v4 = last4["tick_volume"].astype(float)
        delta_pct = float(((cloc4 * v4).sum() / max(float(v4.sum()), 1.0)) * 100.0)

        return {"delta_pct": round(delta_pct, 2), "inside_poc_chop": bool(inside_chop)}

    def sync_whipsaw_and_streaks(self):
        ref_tick = mt5.symbol_info_tick("EURUSD")
        now_ts = int(ref_tick.time) if ref_tick else int(time.time())
        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        deals = mt5.history_deals_get(now_dt - timedelta(hours=4), now_dt + timedelta(hours=3)) or []
        changed = False
        for d in sorted(deals, key=lambda x: x.time):
            if d.entry == 1 and d.ticket not in self.processed_deals:
                self.processed_deals.add(d.ticket)
                if d.symbol in CORE_TRIAD and 0 <= (now_ts - d.time) <= 7200:
                    if d.profit < -0.10:
                        self.win_streak[d.symbol] = 0
                        changed = True
                        if self.whipsaw:
                            self.whipsaw.record_loss(d.symbol)
                    elif d.profit > 0.10:
                        self.win_streak[d.symbol] = min(3, int(self.win_streak.get(d.symbol, 0)) + 1)
                        changed = True
                        if self.whipsaw:
                            self.whipsaw.record_win(d.symbol)
        if changed:
            self._save_win_streak()

    def whipsaw_allowed(self, sym: str) -> bool:
        if not self.whipsaw:
            return True
        for fn_name in ("is_allowed", "allow_trade", "can_trade", "check"):
            fn = getattr(self.whipsaw, fn_name, None)
            if callable(fn):
                res = fn(sym)
                return res[0] if isinstance(res, tuple) else bool(res)
        return True

    def enforce_per_symbol_oco(self, positions, orders):
        active_syms = {p.symbol for p in positions}
        for o in orders:
            if o.symbol in active_syms:
                res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    logging.info(f"[V4.4 OCO] Cancelled opposite pending leg #{o.ticket} on {o.symbol}.")

    def get_h1_trend(self, sym: str) -> tuple[bool, bool]:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 1, 60)
        if rates is None or len(rates) < 50:
            return False, False
        closes = pd.Series([float(r["close"]) for r in rates])
        ema20 = closes.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = closes.ewm(span=50, adjust=False).mean().iloc[-1]
        c = closes.iloc[-1]
        return bool(c > ema20 and ema20 > ema50), bool(c < ema20 and ema20 < ema50)

    def get_m15_volume_ratio(self, sym: str) -> float:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 22)
        if rates is None or len(rates) < 21:
            return 1.0
        vols = np.array([float(r["tick_volume"]) for r in rates])
        avg_prev = np.mean(vols[:-1])
        return float(vols[-1] / avg_prev) if avg_prev > 0 else 1.0

    def get_prior_day_hl(self, sym: str, date_str: str) -> tuple[float, float]:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 1, 3)
        if rates is None or len(rates) == 0:
            return 1e12, -1e12
        last_bar = rates[-1]
        return float(last_bar["high"]), float(last_bar["low"])

    def compute_coiled_session_box(self, sym: str, srv_dt: datetime):
        date_str = srv_dt.strftime("%Y-%m-%d")
        key = (date_str, sym)
        if key in self.daily_box_cache:
            return self.daily_box_cache[key]

        if srv_dt.hour < 4:
            return None

        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 1, 200)
        if rates is None or len(rates) < 60:
            return None

        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)

        prev_c = df["close"].shift(1)
        tr = np.maximum(df["high"] - df["low"], np.maximum((df["high"] - prev_c).abs(), (df["low"] - prev_c).abs()))
        df["atr20"] = tr.rolling(20).mean()
        df["atr56"] = tr.rolling(56).mean()

        today_bars = df[df["dt"].dt.strftime("%Y-%m-%d") == date_str]
        if len(today_bars) < 16:
            return None

        ref = today_bars.iloc[:16]
        ref_high = float(ref["high"].max())
        ref_low = float(ref["low"].min())
        atr_box = float(ref["atr20"].iloc[-1])
        atr_56 = float(ref["atr56"].iloc[-1])
        if np.isnan(atr_box) or np.isnan(atr_56) or atr_box <= 0 or atr_56 <= 0:
            return None

        box_range = ref_high - ref_low
        max_mult = COMPRESSION_MULT.get(sym, 4.8)
        if box_range > (atr_56 * max_mult) or box_range < (atr_box * 0.6):
            self.daily_box_cache[key] = None
            logging.info(f"[V4.4 SKIP NON-COILED] {sym} Asian box={box_range:.5f} vs {max_mult}x ATR56={atr_56 * max_mult:.5f}")
            return None

        buf_dist = atr_box * 0.40
        sl_dist = atr_box * 1.25
        pdh, pdl = self.get_prior_day_hl(sym, date_str)
        box = {
            "ref_high": ref_high,
            "ref_low": ref_low,
            "atr_box": atr_box,
            "buy_stop": ref_high + buf_dist,
            "sell_stop": ref_low - buf_dist,
            "sl_dist": sl_dist,
            "pdh": pdh,
            "pdl": pdl,
        }
        self.daily_box_cache[key] = box
        logging.info(f"[V4.4 COILED BOX LOCKED] {sym} Range=[{ref_low:.2f}..{ref_high:.2f}] | BuyStop={box['buy_stop']:.2f} | SellStop={box['sell_stop']:.2f} | PDH={pdh:.2f} | PDL={pdl:.2f}")
        return box

    def calc_anti_martingale_lot(self, sym: str, info, equity: float, sl_dist: float) -> float:
        usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
        scale = 1.35 if int(self.win_streak.get(sym, 0)) >= 1 else 1.0
        risk_usd = max(10.0, equity * BASE_RISK_PCT * scale)
        raw_lot = risk_usd / max(sl_dist * usd_per_unit, 1e-6)
        step = info.volume_step if info.volume_step > 0 else 0.01
        lot = round(raw_lot / step) * step
        return round(max(info.volume_min, min(0.30, lot)), 2)

    def close_non_harvested_eod(self, positions, srv_dt: datetime):
        # Gap 1: Close non-harvested trades at 22:45 UTC; allow +1.60R harvested runners to ride multi-session!
        if srv_dt.hour == 22 and srv_dt.minute >= 45:
            for p in positions:
                if p.magic in LEGACY_MAGICS:
                    is_buy = (p.type == mt5.POSITION_TYPE_BUY)
                    already_harvested = (is_buy and p.sl > p.price_open) or (not is_buy and p.sl > 0 and p.sl < p.price_open)
                    if already_harvested:
                        logging.info(f"[V4.4 MULTI-SESSION RUNNER HOLD] Retaining harvested runner {p.symbol} #{p.ticket} (SL={p.sl} locked in profit).")
                        continue
                    tick = mt5.symbol_info_tick(p.symbol)
                    if not tick:
                        continue
                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL,
                        "position": p.ticket,
                        "symbol": p.symbol,
                        "volume": p.volume,
                        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                        "price": tick.bid if is_buy else tick.ask,
                        "deviation": 30,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                        "comment": "NEXUS_V44_EOD_FLAT_CLOSE",
                    })
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        logging.info(f"[V4.4 EOD FLAT CLOSE] Closed non-runner {p.symbol} #{p.ticket} PnL=${p.profit:+.2f}")
                        send_v43_alert(
                            f"🏁 <b>[V4.4 EOD SESSION CLOSE]</b>\n"
                            f"Asset: <b>{p.symbol}</b> (#{p.ticket})\n"
                            f"Volume: {p.volume}L | Realized PnL: <b>${p.profit:+.2f}</b>"
                        )
                    else:
                        logging.warning(f"[V4.4 SELL_STOP REJECTED] {sym} {lot}L @ {round(box['sell_stop'], info.digits)} | retcode={getattr(res, 'retcode', None)} | comment={getattr(res, 'comment', mt5.last_error())}")


    def manage_tiered_profit_protection(self, positions):
        if not positions:
            return
        be_state_path = Path(r"C:\Quant-Nexus-Eng\t2_breakeven_state.json")
        try:
            scaled = set(json.loads(be_state_path.read_text(encoding="utf-8")).get("scaled_tickets", [])) if be_state_path.exists() else set()
        except Exception:
            scaled = set()

        active_ids = {p.ticket for p in positions}
        if scaled - active_ids:
            scaled &= active_ids
            try:
                be_state_path.write_text(json.dumps({"scaled_tickets": list(scaled)}, indent=2), encoding="utf-8")
            except Exception:
                pass

        pad_map = {"EURUSD": 12, "GBPUSD": 15, "USDJPY": 15, "USDCHF": 15, "USDCAD": 15, "XAUUSD": 60, "BTCUSD": 300, "US30": 30}
        for p in positions:
            sym = p.symbol
            info = mt5.symbol_info(sym)
            if not info:
                continue
            is_buy = (p.type == mt5.POSITION_TYPE_BUY)
            open_px = float(p.price_open)
            mark = float(p.price_current)
            sl = float(p.sl)
            vol = float(p.volume)
            digits, pt = info.digits, info.point
            pad = pad_map.get(sym.rstrip("m"), 20) * pt
            init_risk = abs(open_px - sl) if (sl > 0 and abs(open_px - sl) > pad) else (200 * pt)
            gain = (mark - open_px) if is_buy else (open_px - mark)
            r_mult = gain / init_risk if init_risk > 0 else 0.0

            # Tier 1: Rapid Breakeven Lock at +0.75R
            if r_mult >= 0.75:
                be_sl = round(open_px + pad if is_buy else open_px - pad, digits)
                eps = 0.5 * pt
                if (is_buy and ((be_sl - sl) > eps or sl == 0.0)) or ((not is_buy) and ((sl - be_sl) > eps or sl == 0.0)):
                    res = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": sym, "sl": be_sl, "tp": p.tp})
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        logging.info(f"[T2 TIER-1 BE-LOCK] #{p.ticket} {sym} +{r_mult:.2f}R -> SL={be_sl}")
                        sl = be_sl

            # Tier 2: 50% Rapid Harvest at +1.40R
            if r_mult >= 1.40 and p.ticket not in scaled:
                step, min_lot = info.volume_step, info.volume_min
                half_vol = round(int((vol / 2.0) / step) * step, 2)
                if half_vol >= min_lot and (vol - half_vol) >= min_lot:
                    fill = mt5.ORDER_FILLING_FOK if (info.filling_mode & 1) else (mt5.ORDER_FILLING_IOC if (info.filling_mode & 2) else mt5.ORDER_FILLING_RETURN)
                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL,
                        "position": p.ticket,
                        "symbol": sym,
                        "volume": half_vol,
                        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                        "price": info.bid if is_buy else info.ask,
                        "deviation": 20,
                        "magic": p.magic,
                        "comment": "T2_Rapid_Harvest_1.4R",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": fill,
                    })
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        scaled.add(p.ticket)
                        try:
                            be_state_path.write_text(json.dumps({"scaled_tickets": list(scaled)}, indent=2), encoding="utf-8")
                        except Exception:
                            pass
                        logging.info(f"[T2 TIER-2 HARVEST] #{p.ticket} {sym} closed 50% ({half_vol}L) at +{r_mult:.2f}R")

            # Tier 3: M5 Candle Trailing Stop (>= +1.20R or post-harvest)
            if r_mult >= 1.20 or p.ticket in scaled:
                m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 1, 2)
                if m5 is not None and len(m5) >= 2:
                    if is_buy:
                        prop_sl = round(min(m5[0]["low"], m5[1]["low"]) - pad, digits)
                        if prop_sl > sl and prop_sl > (open_px + pad):
                            res = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": sym, "sl": prop_sl, "tp": p.tp})
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                logging.info(f"[T2 TIER-3 M5 TRAIL] #{p.ticket} {sym} BUY SL -> {prop_sl}")
                    else:
                        prop_sl = round(max(m5[0]["high"], m5[1]["high"]) + pad, digits)
                        if (sl == 0.0 or prop_sl < sl) and prop_sl < (open_px - pad):
                            res = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": sym, "sl": prop_sl, "tp": p.tp})
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                logging.info(f"[T2 TIER-3 M5 TRAIL] #{p.ticket} {sym} SELL SL -> {prop_sl}")

    def cycle(self):
        acc = mt5.account_info()
        if not acc:
            return

        positions = mt5.positions_get() or []
        orders = mt5.orders_get() or []

        ref_tick = mt5.symbol_info_tick("XAUUSD")
        srv_dt = datetime.fromtimestamp(ref_tick.time, tz=timezone.utc) if ref_tick else datetime.now(timezone.utc)

        self.sync_whipsaw_and_streaks()
        self.enforce_per_symbol_oco(positions, orders)
        self.manage_tiered_profit_protection(positions)
        self.close_non_harvested_eod(positions, srv_dt)

        engaged_syms = {p.symbol for p in positions} | {o.symbol for o in orders}
        if len(engaged_syms) >= MAX_ACTIVE_ASSETS:
            return

        # Gap 3: Macro News Shield (13:15-13:45 UTC) + Institutional London/NY Killzone Window (07:00-15:59 UTC)
        in_news = (srv_dt.hour == 13 and 15 <= srv_dt.minute <= 45)
        in_killzone = (7 <= srv_dt.hour <= 15)
        if in_news or not in_killzone:
            return

        date_str = srv_dt.strftime("%Y-%m-%d")

        for sym in CORE_TRIAD:
            if len(engaged_syms) >= MAX_ACTIVE_ASSETS:
                break
            if sym in engaged_syms or (date_str, sym) in self.daily_traded:
                continue
            if not self.whipsaw_allowed(sym):
                continue

            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym)
            if not info or not tick:
                continue

            box = self.compute_coiled_session_box(sym, srv_dt)
            if not box:
                continue

            micro = self.read_microstructure(sym)
            delta_pct = float(micro.get("delta_pct", 0.0))
            inside_chop = bool(micro.get("inside_poc_chop", False))
            if inside_chop:
                continue

            # Gap 2, 3 & 4: Relative M15 Volume + Symmetric H1 Trend + PDH/PDL Wall Clearance
            vol_ratio = self.get_m15_volume_ratio(sym)
            h1_bull, h1_bear = self.get_h1_trend(sym)
            sl_dist = box["sl_dist"]
            chase_cap = sl_dist * 0.40
            pdh_clear = (box["pdh"] <= box["buy_stop"]) or ((box["pdh"] - box["buy_stop"]) >= sl_dist * 0.90)
            pdl_clear = (box["pdl"] >= box["sell_stop"]) or ((box["sell_stop"] - box["pdl"]) >= sl_dist * 0.90)

            lot = self.calc_anti_martingale_lot(sym, info, acc.equity, sl_dist)
            lot = max(info.volume_min, min(info.volume_max, round(round(lot / info.volume_step) * info.volume_step, 2)))
            fill_type = (
                mt5.ORDER_FILLING_FOK if (info.filling_mode & 1)
                else (mt5.ORDER_FILLING_IOC if (info.filling_mode & 2) else mt5.ORDER_FILLING_RETURN)
            )
            exp_time = int(tick.time) + 3600

            # 1A. Bullish Pre-Breakout Pending BUY_STOP (Price inside box + H1 Bull + Delta >= +8% + PDH Clear)
            if h1_bull and delta_pct >= 8.0 and pdh_clear and tick.ask < box["buy_stop"]:
                sl_buy = round(box["buy_stop"] - sl_dist, info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY_STOP,
                    "price": round(box["buy_stop"], info.digits),
                    "sl": sl_buy,
                    "deviation": 30,
                    "magic": MAGIC_NUMBER,
                    "type_time": mt5.ORDER_TIME_SPECIFIED,
                    "expiration": exp_time,
                    "type_filling": fill_type,
                    "comment": "NEXUS_V44_INST_BUY",
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    engaged_syms.add(sym)
                    self.daily_traded.add((date_str, sym))
                    logging.info(f"[V4.4 INST BUY ARMED] {sym} {lot}L BUY_STOP @ {round(box['buy_stop'], info.digits)} | SL={sl_buy} | Delta={delta_pct:+.1f}% | Vol={vol_ratio:.2f}x (#{res.order})")
                    send_v43_alert(
                        f"🚀 <b>[V4.4 INSTITUTIONAL BUY ARMED]</b>\n"
                        f"Asset: <b>{sym}</b> ({lot}L) | Ticket: #{res.order}\n"
                        f"Entry Stop: <code>{round(box['buy_stop'], info.digits)}</code> | SL: <code>{sl_buy}</code>\n"
                        f"H1: <b>BULL</b> | Delta: <b>{delta_pct:+.1f}%</b> | Vol: <b>{vol_ratio:.2f}x</b>"
                    )
                    continue
                else:
                    logging.warning(f"[V4.4 BUY_STOP REJECTED] {sym} {lot}L @ {round(box['buy_stop'], info.digits)} | retcode={getattr(res, 'retcode', None)} | comment={getattr(res, 'comment', mt5.last_error())}")

            # 1B. Bullish At-Breakout Instant Market Execution (Crossed buy_stop within chase_cap + Delta >= +18% + Vol >= 1.15x)
            if h1_bull and delta_pct >= 18.0 and vol_ratio >= 1.15 and pdh_clear and box["buy_stop"] <= tick.ask <= (box["buy_stop"] + chase_cap):
                sl_buy = round(tick.ask - sl_dist, info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY,
                    "price": tick.ask,
                    "sl": sl_buy,
                    "deviation": 30,
                    "magic": MAGIC_NUMBER,
                    "type_filling": fill_type,
                    "comment": "NEXUS_V44_MKT_BUY",
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    engaged_syms.add(sym)
                    self.daily_traded.add((date_str, sym))
                    logging.info(f"[V4.4 BREAKOUT BUY FILLED] {sym} {lot}L MKT_BUY @ {tick.ask} | SL={sl_buy} | Delta={delta_pct:+.1f}% | Vol={vol_ratio:.2f}x (#{res.order})")
                    send_v43_alert(
                        f"⚡ <b>[V4.4 BREAKOUT BUY FILLED]</b>\n"
                        f"Asset: <b>{sym}</b> ({lot}L) | Ticket: #{res.order}\n"
                        f"Fill Price: <code>{tick.ask}</code> | SL: <code>{sl_buy}</code>\n"
                        f"H1: <b>BULL</b> | Delta: <b>{delta_pct:+.1f}%</b> | Vol: <b>{vol_ratio:.2f}x</b>"
                    )
                    continue
                else:
                    logging.warning(f"[V4.4 MKT_BUY REJECTED] {sym} {lot}L @ {tick.ask} | retcode={getattr(res, 'retcode', None)} | comment={getattr(res, 'comment', mt5.last_error())}")

            # 2A. Bearish Pre-Breakout Pending SELL_STOP (Price inside box + H1 Bear + Delta <= -8% + PDL Clear)
            if h1_bear and delta_pct <= -8.0 and pdl_clear and tick.bid > box["sell_stop"]:
                sl_sell = round(box["sell_stop"] + sl_dist, info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_PENDING,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_SELL_STOP,
                    "price": round(box["sell_stop"], info.digits),
                    "sl": sl_sell,
                    "deviation": 30,
                    "magic": MAGIC_NUMBER,
                    "type_time": mt5.ORDER_TIME_SPECIFIED,
                    "expiration": exp_time,
                    "type_filling": fill_type,
                    "comment": "NEXUS_V44_INST_SELL",
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    engaged_syms.add(sym)
                    self.daily_traded.add((date_str, sym))
                    logging.info(f"[V4.4 INST SELL ARMED] {sym} {lot}L SELL_STOP @ {round(box['sell_stop'], info.digits)} | SL={sl_sell} | Delta={delta_pct:+.1f}% | Vol={vol_ratio:.2f}x (#{res.order})")
                    send_v43_alert(
                        f"🔻 <b>[V4.4 INSTITUTIONAL SELL ARMED]</b>\n"
                        f"Asset: <b>{sym}</b> ({lot}L) | Ticket: #{res.order}\n"
                        f"Entry Stop: <code>{round(box['sell_stop'], info.digits)}</code> | SL: <code>{sl_sell}</code>\n"
                        f"H1: <b>BEAR</b> | Delta: <b>{delta_pct:+.1f}%</b> | Vol: <b>{vol_ratio:.2f}x</b>"
                    )
                    continue
                else:
                    logging.warning(f"[V4.4 SELL_STOP REJECTED] {sym} {lot}L @ {round(box['sell_stop'], info.digits)} | retcode={getattr(res, 'retcode', None)} | comment={getattr(res, 'comment', mt5.last_error())}")

            # 2B. Bearish At-Breakout Instant Market Execution (Crossed sell_stop within chase_cap + Delta <= -18% + Vol >= 1.15x)
            if h1_bear and delta_pct <= -18.0 and vol_ratio >= 1.15 and pdl_clear and (box["sell_stop"] - chase_cap) <= tick.bid <= box["sell_stop"]:
                sl_sell = round(tick.bid + sl_dist, info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": sym,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_SELL,
                    "price": tick.bid,
                    "sl": sl_sell,
                    "deviation": 30,
                    "magic": MAGIC_NUMBER,
                    "type_filling": fill_type,
                    "comment": "NEXUS_V44_MKT_SELL",
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    engaged_syms.add(sym)
                    self.daily_traded.add((date_str, sym))
                    logging.info(f"[V4.4 BREAKOUT SELL FILLED] {sym} {lot}L MKT_SELL @ {tick.bid} | SL={sl_sell} | Delta={delta_pct:+.1f}% | Vol={vol_ratio:.2f}x (#{res.order})")
                    send_v43_alert(
                        f"⚡ <b>[V4.4 BREAKOUT SELL FILLED]</b>\n"
                        f"Asset: <b>{sym}</b> ({lot}L) | Ticket: #{res.order}\n"
                        f"Fill Price: <code>{tick.bid}</code> | SL: <code>{sl_sell}</code>\n"
                        f"H1: <b>BEAR</b> | Delta: <b>{delta_pct:+.1f}%</b> | Vol: <b>{vol_ratio:.2f}x</b>"
                    )
                    continue
                else:
                    logging.warning(f"[V4.4 MKT_SELL REJECTED] {sym} {lot}L @ {tick.bid} | retcode={getattr(res, 'retcode', None)} | comment={getattr(res, 'comment', mt5.last_error())}")

    def run(self):
        if not self.connect_mt5():
            sys.exit(1)
        logging.info("=" * 96)
        logging.info("NEXUS ENGINE V4.4 PRODUCTION ONLINE (SYMMETRIC H1+DELTA | KILLZONE VOL | PDH/PDL CLEARANCE | MULTI-SESSION RUNNERS)")
        logging.info("=" * 96)
        while True:
            try:
                _emit_m15_heartbeat(datetime.now(timezone.utc), locals().get('daily_box_cache', {}), locals().get('ms_data') or locals().get('microstructure') or {})
            except Exception as hb_err:
                logging.warning(f'[V4.4 M15 HB WARN] {hb_err}')
            try:
                self.cycle()
            except Exception as e:
                logging.error(f"Cycle exception: {e}")
            time.sleep(3)


_LAST_M15_HB_BUCKET = None

def _emit_m15_heartbeat(now_utc, daily_box_cache, ms_raw):
    global _LAST_M15_HB_BUCKET
    bucket = (now_utc.year, now_utc.month, now_utc.day, now_utc.hour, now_utc.minute // 15)
    if bucket == _LAST_M15_HB_BUCKET:
        return
    _LAST_M15_HB_BUCKET = bucket
    ai = mt5.account_info()
    eq = f"${ai.equity:,.2f}" if ai else "N/A"
    pos_cnt = mt5.positions_total()
    kz = "KZ:ON" if (7 <= now_utc.hour <= 15) else "KZ:OFF"
    ms_fleet = ms_raw.get("fleet", ms_raw) if isinstance(ms_raw, dict) else {}
    armed_parts, skipped_syms = [], []
    today_key = now_utc.date()
    for sym in CORE_TRIAD:
        box = None
        if isinstance(daily_box_cache, dict):
            for k, v in daily_box_cache.items():
                if isinstance(v, dict) and "buy_stop" in v and (
                    k == sym
                    or (isinstance(k, tuple) and sym in k and today_key in k)
                    or (isinstance(k, str) and sym in k)
                ):
                    box = v
                    break
        if not box:
            skipped_syms.append(sym)
            continue
        tick = mt5.symbol_info_tick(sym)
        info = mt5.symbol_info(sym)
        if not tick or not info:
            skipped_syms.append(sym)
            continue
        d = info.digits
        dist_buy = box["buy_stop"] - tick.ask
        dist_sell = tick.bid - box["sell_stop"]
        ms = ms_fleet.get(sym, {}) if isinstance(ms_fleet, dict) else {}
        delta = float(ms.get("delta_pct", 0.0)) if isinstance(ms, dict) else 0.0
        armed_parts.append(f"{sym}[Bid={tick.bid:.{d}f} | dBuy={dist_buy:+.{d}f} | dSell={dist_sell:+.{d}f} | dPct={delta:+.1f}%]")
    armed_str = " ; ".join(armed_parts) if armed_parts else "None"
    skip_str = ",".join(skipped_syms) if skipped_syms else "None"
    logging.info(f"[V4.4 M15 HEARTBEAT] {now_utc.strftime('%H:%M')} UTC ({kz}) | Eq={eq} | Pos={pos_cnt} | ARMED: {armed_str} | SKIP: {skip_str}")

if __name__ == "__main__":
    QuantNexusV44Daemon().run()
