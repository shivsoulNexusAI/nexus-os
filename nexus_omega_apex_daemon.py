import os
import sys
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import httpx
import MetaTrader5 as mt5

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")
TERMINAL = r"C:/MT5_Quant_278017866/terminal64.exe"
LOG_FILE = BASE_DIR / "nexus_omega_apex.log"
STATE_FILE = BASE_DIR / "omega_apex_state.json"
MICRO_STATE = BASE_DIR / "microstructure_state.json"
TG_CONFIG = BASE_DIR / "t2_telegram_config.json"

MAGIC_NUMBER = 44044
BASE_RISK_PCT = 0.013
DAILY_DD_LIMIT_PCT = 0.025  # 2.5% daily equity circuit breaker
PORTFOLIO_6 = ["XAUUSD", "BTCUSD", "US30", "EURUSD", "USDCHF", "USDCAD"]
USD_CORRELATED = {"EURUSD", "USDCHF", "USDCAD"}

MICRO_CFG = {
    "XAUUSD": {"step_mult": 25,  "lookback_sec": 300, "absorb_hurdle": 22.0},
    "BTCUSD": {"step_mult": 100, "lookback_sec": 300, "absorb_hurdle": 22.0},
    "US30":   {"step_mult": 20,  "lookback_sec": 300, "absorb_hurdle": 22.0},
    "EURUSD": {"step_mult": 5,   "lookback_sec": 300, "absorb_hurdle": 24.0},
    "USDCHF": {"step_mult": 5,   "lookback_sec": 300, "absorb_hurdle": 24.0},
    "USDCAD": {"step_mult": 5,   "lookback_sec": 300, "absorb_hurdle": 24.0},
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [OMEGA-APEX] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("OmegaApexElite")


def send_tg(msg: str):
    if not TG_CONFIG.exists():
        return
    try:
        cfg = json.loads(TG_CONFIG.read_text(encoding="utf-8"))
        token, chat_id = cfg.get("bot_token"), cfg.get("authorized_chat_id")
        if token and chat_id:
            with httpx.Client(timeout=5.0) as c:
                c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
    except Exception:
        pass


class OmegaApexEliteEngine:
    """
    Omega Apex Elite Production Daemon (Magic=44044):
      1. M5-Verified Variant #4 Coiled Asian Box (00:00..03:45 UTC, 3.4/2.6 ATR bounds) + H1 EMA20/50 Trend
      2. Live Quote-Shift Footprint Delta + 5m VPOC/VAH/VAL Anti-Chop & Absorption Exit Protection
      3. Dynamic Killzone Re-Arming (London 07:00-10:59 UTC & NY 13:45-15:59 UTC)
      4. Closed-Loop Deal Telemetry Sync, Strict Per-Symbol OCO, USD Correlation Cap & 2.5% Daily Circuit Breaker
    """

    def __init__(self):
        self.state = self._load_state()
        self.last_hb_min = -1

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "day_str": "",
            "day_start_equity": 0.0,
            "circuit_tripped": False,
            "win_streak": {},
            "consec_losses": {},
            "skip_date": {},
            "processed_deals": [],
            "t1_done": [],
            "t2_done": [],
            "absorb_locked": [],
            "peak_dist": {},
            "sl_dist": {},
        }

    def _save_state(self):
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)

    def ensure_connected(self) -> bool:
        if mt5.terminal_info() is not None and mt5.account_info() is not None:
            return True
        for attempt in range(1, 4):
            if mt5.initialize(path=TERMINAL, portable=False) and mt5.account_info() is not None:
                log.info("MT5 IPC connected (attempt %d).", attempt)
                return True
            time.sleep(2.0 * attempt)
        log.error("MT5 IPC connection failed: %s", mt5.last_error())
        return False

    def resolve_symbol(self, base: str) -> str | None:
        if mt5.symbol_info(base) is not None:
            return base
        for s in (mt5.symbols_get() or []):
            if s.name.startswith(base) and len(s.name) <= len(base) + 2 and s.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
                return s.name
        return None

    def get_footprint_microstructure(self, sym: str, base: str) -> dict | None:
        # 1. Try fresh microstructure_state.json first (< 15s old)
        if MICRO_STATE.exists():
            try:
                raw = json.loads(MICRO_STATE.read_text(encoding="utf-8"))
                ts = datetime.fromisoformat(raw.get("timestamp", ""))
                if (datetime.now() - ts).total_seconds() <= 15.0 and base in raw.get("fleet", {}):
                    return raw["fleet"][base]
            except Exception:
                pass

        # 2. Direct live Quote-Shift Tick Rule + 5m VPOC/VAH/VAL fallback
        cfg = MICRO_CFG.get(base, {"step_mult": 10, "lookback_sec": 300, "absorb_hurdle": 22.0})
        info = mt5.symbol_info(sym)
        if not info:
            return None
        now = datetime.now()
        ticks = mt5.copy_ticks_range(sym, now - timedelta(seconds=cfg["lookback_sec"]), now, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) < 15:
            return None

        bids = ticks["bid"].astype(np.float64)
        asks = ticks["ask"].astype(np.float64)
        vols = ticks["volume_ext"].astype(np.float64) if "volume_ext" in ticks.dtype.names else ticks["volume"].astype(np.float64)
        vols = np.where(vols > 0, vols, 1.0)

        mid_shift = (np.diff(bids) + np.diff(asks)) * 0.5
        step_vols = vols[1:]
        buy_vol = float(np.sum(step_vols[mid_shift > 0]))
        sell_vol = float(np.sum(step_vols[mid_shift < 0]))
        active_vol = buy_vol + sell_vol
        delta_pct = (buy_vol - sell_vol) / active_vol * 100.0 if active_vol > 0 else 0.0

        step = info.point * cfg["step_mult"]
        binned = np.round(np.round(bids[1:] / step) * step, info.digits)
        uniq, inv = np.unique(binned, return_inverse=True)
        bvols = np.bincount(inv, weights=step_vols)
        poc_idx = int(np.argmax(bvols))
        vpoc = float(uniq[poc_idx])
        mid_now = float((bids[-1] + asks[-1]) * 0.5)
        inside_poc_chop = abs(mid_now - vpoc) <= (step * 1.5)

        return {
            "vpoc": round(vpoc, info.digits),
            "current_mid": round(mid_now, info.digits),
            "inside_poc_chop": bool(inside_poc_chop),
            "ticks": int(len(ticks)),
            "delta_pct": round(delta_pct, 2),
        }

    def sync_closed_deals_and_circuit_breaker(self, acc, now_utc: datetime) -> bool:
        today_str = now_utc.strftime("%Y-%m-%d")
        if self.state.get("day_str") != today_str or self.state.get("day_start_equity", 0.0) <= 0:
            self.state["day_str"] = today_str
            self.state["day_start_equity"] = float(acc.equity)
            self.state["circuit_tripped"] = False
            log.info("[DAILY RESET] %s | Start Equity=$%.2f", today_str, acc.equity)

        # Sync closed Magic=44044 deals to update win_streak & 2-loss daily skip
        deals = mt5.history_deals_get(now_utc - timedelta(days=3), now_utc + timedelta(hours=2)) or []
        seen = set(self.state.get("processed_deals", []))
        for d in sorted(deals, key=lambda x: x.time):
            if d.magic != MAGIC_NUMBER or d.entry not in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY):
                continue
            if d.ticket in seen:
                continue
            seen.add(d.ticket)
            base = next((b for b in PORTFOLIO_6 if d.symbol.startswith(b)), d.symbol)
            net = float(d.profit + d.swap + d.commission)
            deal_day = datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%Y-%m-%d")
            if net > 0:
                self.state["win_streak"][base] = self.state["win_streak"].get(base, 0) + 1
                self.state["consec_losses"][base] = 0
            elif net < 0:
                self.state["win_streak"][base] = 0
                cl = self.state["consec_losses"].get(base, 0) + 1
                self.state["consec_losses"][base] = cl
                if cl >= 2:
                    self.state["skip_date"][base] = deal_day
                    self.state["consec_losses"][base] = 0
                    log.warning("[2-LOSS COOLDOWN] %s paused for %s after 2 consecutive losses.", base, deal_day)
            log.info("[DEAL SYNC] #%s %s Net=$%+.2f | Streak=%d", d.ticket, base, net, self.state["win_streak"].get(base, 0))

        self.state["processed_deals"] = list(seen)[-500:]

        # Check 2.5% Daily Equity Circuit Breaker
        start_eq = float(self.state["day_start_equity"])
        dd_pct = (start_eq - float(acc.equity)) / max(start_eq, 1.0)
        if dd_pct >= DAILY_DD_LIMIT_PCT:
            if not self.state["circuit_tripped"]:
                self.state["circuit_tripped"] = True
                log.critical("[CIRCUIT BREAKER TRIPPED] Daily DD %.2f%% >= %.2f%% ($%.2f -> $%.2f). Halting new entries!",
                             dd_pct * 100, DAILY_DD_LIMIT_PCT * 100, start_eq, acc.equity)
                send_tg(f"<b>OMEGA APEX CIRCUIT BREAKER</b>\nDaily DD: <code>-{dd_pct*100:.2f}%</code>\nNew entries halted for {today_str}.")
            self._save_state()
            return False

        self._save_state()
        return True

    def compute_setup(self, sym: str, base: str) -> dict | None:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 160)
        rh1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 80)
        rd1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5)
        if not info or r15 is None or len(r15) < 80 or rh1 is None or len(rh1) < 55 or rd1 is None or len(rd1) < 2:
            return None

        max_mult = 3.4 if "XAU" in base else 2.6
        df = pd.DataFrame(r15)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["date"] = df["dt"].dt.date

        dfh1 = pd.DataFrame(rh1)
        dfh1["ema20"] = dfh1["close"].ewm(span=20, adjust=False).mean()
        dfh1["ema50"] = dfh1["close"].ewm(span=50, adjust=False).mean()
        h1_prev = dfh1.iloc[-2]
        h1_bull = bool((h1_prev["close"] > h1_prev["ema20"]) and (h1_prev["ema20"] > h1_prev["ema50"]))
        h1_bear = bool((h1_prev["close"] < h1_prev["ema20"]) and (h1_prev["ema20"] < h1_prev["ema50"]))

        pdh = float(rd1[-2]["high"])
        pdl = float(rd1[-2]["low"])

        prev_c = df["close"].shift(1)
        tr = np.maximum(df["high"] - df["low"], np.maximum((df["high"] - prev_c).abs(), (df["low"] - prev_c).abs()))
        df["atr20"] = tr.rolling(20).mean().bfill()
        df["atr56"] = tr.rolling(56).mean().bfill()

        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["tick_volume"].astype(float)
        vol_ratio_prev = float((vol / np.maximum(vol.rolling(20).mean(), 1.0)).iloc[-2])
        vpoc_m15 = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
        va_std = typical.rolling(16).std().fillna(df["atr20"])
        m15_chop_prev = bool(abs(df["close"].iloc[-2] - vpoc_m15.iloc[-2]) <= (0.20 * va_std.iloc[-2]))

        today_date = df["date"].iloc[-1]
        today_df = df[df["date"] == today_date]
        if len(today_df) < 16:
            return None

        ref = today_df.iloc[:16]
        ref_high = float(ref["high"].max())
        ref_low = float(ref["low"].min())
        atr_box = float(ref["atr20"].iloc[-1])
        atr_56 = float(ref["atr56"].iloc[-1])
        box_rng = ref_high - ref_low
        box_ready = (atr_box > 0) and (atr_56 > 0) and ((atr_box * 0.60) <= box_rng <= (atr_56 * max_mult))

        buf_dist = atr_box * 0.40
        sl_dist = atr_box * 1.25
        buy_stop = round(ref_high + buf_dist, info.digits)
        sell_stop = round(ref_low - buf_dist, info.digits)

        fp = self.get_footprint_microstructure(sym, base)
        tick_delta = float(fp["delta_pct"]) if fp else 0.0
        tick_chop = bool(fp["inside_poc_chop"]) if fp else False

        return {
            "base": base,
            "sym": sym,
            "info": info,
            "today_str": str(today_date),
            "box_ready": box_ready,
            "buy_stop": buy_stop,
            "sell_stop": sell_stop,
            "sl_dist": sl_dist,
            "h1_bull": h1_bull,
            "h1_bear": h1_bear,
            "m15_chop": m15_chop_prev,
            "tick_chop": tick_chop,
            "vol_ratio": vol_ratio_prev,
            "tick_delta": tick_delta,
            "pdh": pdh,
            "pdl": pdl,
        }

    def calc_lot(self, base: str, info, equity: float, sl_dist: float) -> float:
        usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
        ws = self.state["win_streak"].get(base, 0)
        scale = 1.35 if ws >= 1 else 1.0
        risk_usd = equity * BASE_RISK_PCT * scale
        raw_lot = risk_usd / max(sl_dist * usd_per_unit, 1e-6)
        step = info.volume_step if info.volume_step > 0 else 0.01
        return max(info.volume_min, min(0.30, round(raw_lot / step) * step))

    def manage_positions_and_orders(self, positions, orders, now_utc: datetime):
        my_pos = [p for p in positions if p.magic == MAGIC_NUMBER]
        my_ord = [o for o in orders if o.magic == MAGIC_NUMBER]

        in_kz = (7 <= now_utc.hour <= 15)
        in_news = (now_utc.hour == 13 and 15 <= now_utc.minute <= 45)
        pos_syms = {p.symbol for p in my_pos}

        # Strict per-symbol OCO: max 1 pending order per symbol, cancel if position open or outside KZ/news
        seen_ord_syms = set()
        for o in my_ord:
            if (o.symbol in pos_syms) or (o.symbol in seen_ord_syms) or (not in_kz) or in_news:
                mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                log.info("[OCO CANCEL] Removed pending %s #%s", o.symbol, o.ticket)
            else:
                seen_ord_syms.add(o.symbol)

        for p in my_pos:
            info = mt5.symbol_info(p.symbol)
            tick = mt5.symbol_info_tick(p.symbol)
            if not info or not tick or p.sl == 0:
                continue
            t_key = str(p.ticket)
            base = next((b for b in PORTFOLIO_6 if p.symbol.startswith(b)), p.symbol)
            sl_dist = self.state["sl_dist"].get(t_key, abs(p.price_open - p.sl))
            self.state["sl_dist"][t_key] = sl_dist

            is_buy = (p.type == mt5.POSITION_TYPE_BUY)
            cur_price = tick.bid if is_buy else tick.ask
            gain = (cur_price - p.price_open) if is_buy else (p.price_open - cur_price)
            peak = max(float(self.state["peak_dist"].get(t_key, 0.0)), gain)
            self.state["peak_dist"][t_key] = peak

            # 1. EOD 22:45 UTC close for non-T2 positions
            if t_key not in self.state["t2_done"] and now_utc.hour == 22 and now_utc.minute >= 45:
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
                    "type": close_type, "position": p.ticket, "price": cur_price,
                    "deviation": 30, "magic": MAGIC_NUMBER, "comment": "APEX_EOD_EXIT",
                })
                log.info("[EOD EXIT] Closed non-T2 %s #%s @ %s", p.symbol, p.ticket, cur_price)
                continue

            # 2. Footprint Absorption Profit Lock (>= +0.75R + sharp opposite Quote-Shift Delta flip)
            if t_key not in self.state["absorb_locked"] and gain >= sl_dist * 0.75:
                fp = self.get_footprint_microstructure(p.symbol, base)
                hurdle = MICRO_CFG.get(base, {}).get("absorb_hurdle", 22.0)
                if fp:
                    d_pct = float(fp["delta_pct"])
                    absorbed = (is_buy and d_pct <= -hurdle) or ((not is_buy) and d_pct >= hurdle)
                    if absorbed:
                        lock_be = round(p.price_open + sl_dist * 0.50, info.digits) if is_buy else round(p.price_open - sl_dist * 0.50, info.digits)
                        if (is_buy and lock_be > p.sl) or (not is_buy and lock_be < p.sl):
                            mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket, "sl": lock_be, "tp": p.tp})
                            self.state["absorb_locked"].append(t_key)
                            log.info("[ABSORPTION LOCK +0.50R] %s #%s Delta=%+.1f%% -> SL=%s", p.symbol, p.ticket, d_pct, lock_be)

            # 3. T1 (+0.85R): move SL to +0.12R
            if t_key not in self.state["t1_done"] and gain >= sl_dist * 0.85:
                new_sl = round(p.price_open + sl_dist * 0.12, info.digits) if is_buy else round(p.price_open - sl_dist * 0.12, info.digits)
                if (is_buy and new_sl > p.sl) or (not is_buy and new_sl < p.sl):
                    mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket, "sl": new_sl, "tp": p.tp})
                    self.state["t1_done"].append(t_key)
                    log.info("[T1 LOCK +0.85R] %s #%s SL -> %s", p.symbol, p.ticket, new_sl)

            # 4. T2 (+1.60R): close 50% volume & move SL to +1.05R
            if t_key not in self.state["t2_done"] and gain >= sl_dist * 1.60:
                h_vol = round(p.volume * 0.5, 2)
                if h_vol >= info.volume_min:
                    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": h_vol,
                        "type": close_type, "position": p.ticket, "price": cur_price,
                        "deviation": 30, "magic": MAGIC_NUMBER, "comment": "APEX_T2_HARVEST",
                    })
                new_sl = round(p.price_open + sl_dist * 1.05, info.digits) if is_buy else round(p.price_open - sl_dist * 1.05, info.digits)
                mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket, "sl": new_sl, "tp": p.tp})
                self.state["t2_done"].append(t_key)
                log.info("[T2 HARVEST +1.60R] %s #%s harvested 50%% & SL -> %s", p.symbol, p.ticket, new_sl)

            # 5. Runner trailing ratchet (>= +2.20R): lock 65% of peak gain
            if t_key in self.state["t2_done"] and peak >= sl_dist * 2.20:
                lock_sl = round(p.price_open + peak * 0.65, info.digits) if is_buy else round(p.price_open - peak * 0.65, info.digits)
                if (is_buy and lock_sl > p.sl) or (not is_buy and lock_sl < p.sl):
                    mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket, "sl": lock_sl, "tp": p.tp})
                    log.info("[RUNNER TRAIL 65%%] %s #%s SL -> %s", p.symbol, p.ticket, lock_sl)

        self._save_state()

    def cycle(self, dry_run: bool = False):
        if not self.ensure_connected():
            return
        now_utc = datetime.now(timezone.utc)
        acc = mt5.account_info()
        if not acc:
            return

        if not self.sync_closed_deals_and_circuit_breaker(acc, now_utc):
            return

        positions = mt5.positions_get() or []
        orders = mt5.orders_get() or []
        if not dry_run:
            self.manage_positions_and_orders(positions, orders, now_utc)

        my_pos = [p for p in positions if p.magic == MAGIC_NUMBER]
        my_ord = [o for o in orders if o.magic == MAGIC_NUMBER]

        # Active Killzones: London (07:00-10:59 UTC) & NY Post-News (13:46-15:59 UTC)
        in_london = (7 <= now_utc.hour <= 10)
        in_ny = (now_utc.hour == 13 and now_utc.minute > 45) or (14 <= now_utc.hour <= 15)
        in_kz = in_london or in_ny

        if dry_run or (now_utc.minute % 15 == 0 and now_utc.minute != self.last_hb_min):
            self.last_hb_min = now_utc.minute
            log.info("[HB] %02d:%02d UTC (KZ:%s) | Eq=$%.2f | ApexPos=%d | ApexOrd=%d",
                     now_utc.hour, now_utc.minute, "ON" if in_kz else "OFF", acc.equity, len(my_pos), len(my_ord))

        # Count active USD-correlated exposure (max 1 concurrent USD major)
        active_usd_count = sum(
            1 for x in (my_pos + my_ord)
            if any(x.symbol.startswith(u) for u in USD_CORRELATED)
        )

        for base in PORTFOLIO_6:
            sym = self.resolve_symbol(base)
            if not sym:
                continue
            sig = self.compute_setup(sym, base)
            if dry_run and sig:
                log.info("  [SCAN] %s | BoxReady=%s | H1=%s | M15Chop=%s | TickChop=%s | Vol=%.2fx | TickDelta=%+.1f%%",
                         base, sig["box_ready"], "BULL" if sig["h1_bull"] else ("BEAR" if sig["h1_bear"] else "FLAT"),
                         sig["m15_chop"], sig["tick_chop"], sig["vol_ratio"], sig["tick_delta"])
            if dry_run or not in_kz or not sig or not sig["box_ready"]:
                continue

            if any(p.symbol == sym for p in my_pos) or any(o.symbol == sym for o in my_ord):
                continue
            if self.state["skip_date"].get(base) == sig["today_str"]:
                continue
            if base in USD_CORRELATED and active_usd_count >= 1:
                continue
            if sig["m15_chop"] or sig["tick_chop"] or sig["vol_ratio"] < 1.15:
                continue

            info = sig["info"]
            tick = mt5.symbol_info_tick(sym)
            if not tick:
                continue

            lot = self.calc_lot(base, info, acc.equity, sig["sl_dist"])
            pdh_clear = (sig["pdh"] <= sig["buy_stop"]) or ((sig["pdh"] - sig["buy_stop"]) >= sig["sl_dist"] * 0.90)
            pdl_clear = (sig["pdl"] >= sig["sell_stop"]) or ((sig["sell_stop"] - sig["pdl"]) >= sig["sl_dist"] * 0.90)

            # Bullish Arming: H1 Bull + Non-Chop + Vol >= 1.15x + Tick Delta not fighting (>-12%)
            if sig["h1_bull"] and tick.ask < sig["buy_stop"] and pdh_clear and sig["tick_delta"] > -12.0:
                sl_buy = round(sig["buy_stop"] - sig["sl_dist"], info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_PENDING, "symbol": sym, "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY_STOP, "price": sig["buy_stop"], "sl": sl_buy,
                    "deviation": 20, "magic": MAGIC_NUMBER, "comment": "OMEGA_APEX_BUY",
                    "type_time": mt5.ORDER_TIME_DAY, "type_filling": mt5.ORDER_FILLING_IOC,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    if base in USD_CORRELATED:
                        active_usd_count += 1
                    log.info("[APEX BUY ARMED] %s %.2fL BUY_STOP @ %s | SL=%s | Vol=%.2fx | TickDelta=%+.1f%% (#%s)",
                             sym, lot, sig["buy_stop"], sl_buy, sig["vol_ratio"], sig["tick_delta"], res.order)

            # Bearish Arming: H1 Bear + Non-Chop + Vol >= 1.15x + Tick Delta not fighting (<+12%)
            elif sig["h1_bear"] and tick.bid > sig["sell_stop"] and pdl_clear and sig["tick_delta"] < 12.0:
                sl_sell = round(sig["sell_stop"] + sig["sl_dist"], info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_PENDING, "symbol": sym, "volume": lot,
                    "type": mt5.ORDER_TYPE_SELL_STOP, "price": sig["sell_stop"], "sl": sl_sell,
                    "deviation": 20, "magic": MAGIC_NUMBER, "comment": "OMEGA_APEX_SELL",
                    "type_time": mt5.ORDER_TIME_DAY, "type_filling": mt5.ORDER_FILLING_IOC,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    if base in USD_CORRELATED:
                        active_usd_count += 1
                    log.info("[APEX SELL ARMED] %s %.2fL SELL_STOP @ %s | SL=%s | Vol=%.2fx | TickDelta=%+.1f%% (#%s)",
                             sym, lot, sig["sell_stop"], sl_sell, sig["vol_ratio"], sig["tick_delta"], res.order)

    def run(self):
        log.info("====================================================================================")
        log.info("OMEGA APEX ELITE PRODUCTION DAEMON ONLINE (MAGIC=44044 | FOOTPRINT + VPOC + DD GUARD)")
        log.info("====================================================================================")
        try:
            while True:
                self.cycle(dry_run=False)
                time.sleep(15)
        except KeyboardInterrupt:
            log.info("Shutdown requested.")
        finally:
            mt5.shutdown()


if __name__ == "__main__":
    eng = OmegaApexEliteEngine()
    if "--dry-run" in sys.argv:
        eng.cycle(dry_run=True)
        mt5.shutdown()
    else:
        eng.run()
