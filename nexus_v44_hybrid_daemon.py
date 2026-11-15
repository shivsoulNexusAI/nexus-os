import os
import sys
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import httpx
import MetaTrader5 as mt5

TERMINAL = r"C:/MT5_Quant_278061453/terminal64.exe"
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\nexus_v44_hybrid.log")
STATE_FILE = Path(r"C:\Quant-Nexus-Eng\v44_certified_state.json")
TG_CONFIG = Path(r"C:\Quant-Nexus-Eng\t2_telegram_config.json")

MAGIC_NUMBER = 44044
BASE_RISK_PCT = 0.013
PORTFOLIO_6 = ["XAUUSD", "BTCUSD", "US30", "EURUSD", "USDCHF", "USDCAD"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("NexusV44M5Verified")


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


class NexusV44M5VerifiedEngine:
    """Variant #4 (1.72 True M5 PF / 2.25 PF in 2026): 07:00 UTC Coiled Box + VPOC Chop Block + Vol >= 1.15."""

    def __init__(self):
        self.state = self._load_state()
        self.last_hb_min = -1

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"win_streak": {}, "consec_losses": {}, "skip_date": {}, "armed_date": {}, "t1_done": [], "t2_done": [], "peak_dist": {}}

    def _save_state(self):
        STATE_FILE.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def connect(self) -> bool:
        if not mt5.initialize(path=TERMINAL, portable=False):
            log.error("MT5 init failed: %s", mt5.last_error())
            return False
        return mt5.account_info() is not None

    def resolve_symbol(self, base: str) -> str | None:
        if mt5.symbol_info(base) is not None:
            return base
        for s in (mt5.symbols_get() or []):
            if s.name.startswith(base) and len(s.name) <= len(base) + 2 and s.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
                return s.name
        return None

    def compute_verified_signal(self, sym: str) -> dict | None:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 160)
        rh1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 80)
        rd1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5)
        if not info or r15 is None or len(r15) < 80 or rh1 is None or len(rh1) < 55 or rd1 is None or len(rd1) < 2:
            return None

        max_mult = 3.4 if "XAU" in sym.upper() else 2.6
        df = pd.DataFrame(r15)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["date"] = df["dt"].dt.date

        # Completed H1 trend (shift 1 completed H1 bar)
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

        # Closed-bar VPOC Chop Gate & Volume Ratio Gate (iloc[-2] = last completed M15 bar)
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["tick_volume"].astype(float)
        vol_ratio_prev = float((vol / np.maximum(vol.rolling(20).mean(), 1.0)).iloc[-2])
        vpoc = (typical * vol).rolling(16).sum() / np.maximum(vol.rolling(16).sum(), 1.0)
        va_std = typical.rolling(16).std().fillna(df["atr20"])
        inside_chop_prev = bool(abs(df["close"].iloc[-2] - vpoc.iloc[-2]) <= (0.20 * va_std.iloc[-2]))

        # First 16 M15 bars (00:00..03:45 UTC Asian Coiled Box)
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

        return {
            "sym": sym,
            "info": info,
            "today_str": str(today_date),
            "box_ready": box_ready,
            "buy_stop": buy_stop,
            "sell_stop": sell_stop,
            "sl_dist": sl_dist,
            "h1_bull": h1_bull,
            "h1_bear": h1_bear,
            "inside_chop": inside_chop_prev,
            "vol_ratio": vol_ratio_prev,
            "pdh": pdh,
            "pdl": pdl,
        }

    def calc_lot(self, sym: str, info, equity: float, sl_dist: float) -> float:
        usd_per_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
        ws = self.state["win_streak"].get(sym, 0)
        scale = 1.35 if ws >= 1 else 1.0
        risk_usd = equity * BASE_RISK_PCT * scale
        raw_lot = risk_usd / max(sl_dist * usd_per_unit, 1e-6)
        step = info.volume_step if info.volume_step > 0 else 0.01
        return max(info.volume_min, min(0.30, round(raw_lot / step) * step))

    def manage_positions_and_orders(self, positions, orders, now_utc: datetime):
        my_pos = [p for p in positions if p.magic == MAGIC_NUMBER]
        my_ord = [o for o in orders if o.magic == MAGIC_NUMBER]

        in_killzone = (7 <= now_utc.hour <= 15)
        in_news = (now_utc.hour == 13 and 15 <= now_utc.minute <= 45)
        pos_syms = {p.symbol for p in my_pos}
        for o in my_ord:
            if (o.symbol in pos_syms) or (not in_killzone) or in_news:
                mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
                log.info("[V4.4 CANCEL PENDING] %s #%s (Killzone/News/Filled)", o.symbol, o.ticket)

        for p in my_pos:
            info = mt5.symbol_info(p.symbol)
            tick = mt5.symbol_info_tick(p.symbol)
            if not info or not tick or p.sl == 0:
                continue
            t_key = str(p.ticket)
            sl_dist = self.state.get("sl_dist", {}).get(t_key, abs(p.price_open - p.sl))
            self.state.setdefault("sl_dist", {})[t_key] = sl_dist

            is_buy = (p.type == mt5.POSITION_TYPE_BUY)
            cur_price = tick.bid if is_buy else tick.ask
            gain = (cur_price - p.price_open) if is_buy else (p.price_open - cur_price)
            prev_peak = float(self.state["peak_dist"].get(t_key, 0.0))
            peak = max(prev_peak, gain)
            self.state["peak_dist"][t_key] = peak

            # EOD 22:45 UTC close for non-T2 positions
            if t_key not in self.state["t2_done"] and now_utc.hour == 22 and now_utc.minute >= 45:
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
                    "type": close_type, "position": p.ticket, "price": cur_price,
                    "deviation": 30, "magic": MAGIC_NUMBER, "comment": "V44_EOD_EXIT",
                })
                log.info("[V4.4 EOD EXIT] Closed non-T2 %s #%s @ %s", p.symbol, p.ticket, cur_price)
                continue

            # T1 (+0.85R): move SL to +0.12R
            if t_key not in self.state["t1_done"] and gain >= sl_dist * 0.85:
                new_sl = round(p.price_open + sl_dist * 0.12, info.digits) if is_buy else round(p.price_open - sl_dist * 0.12, info.digits)
                if (is_buy and new_sl > p.sl) or (not is_buy and new_sl < p.sl):
                    mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket, "sl": new_sl, "tp": p.tp})
                    self.state["t1_done"].append(t_key)
                    log.info("[V4.4 T1 LOCK +0.85R] %s #%s SL -> %s", p.symbol, p.ticket, new_sl)

            # T2 (+1.60R): close 50% volume & move SL to +1.05R
            if t_key not in self.state["t2_done"] and gain >= sl_dist * 1.60:
                h_vol = round(p.volume * 0.5, 2)
                if h_vol >= info.volume_min:
                    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": h_vol,
                        "type": close_type, "position": p.ticket, "price": cur_price,
                        "deviation": 30, "magic": MAGIC_NUMBER, "comment": "V44_T2_HARVEST",
                    })
                new_sl = round(p.price_open + sl_dist * 1.05, info.digits) if is_buy else round(p.price_open - sl_dist * 1.05, info.digits)
                mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket, "sl": new_sl, "tp": p.tp})
                self.state["t2_done"].append(t_key)
                log.info("[V4.4 T2 HARVEST +1.60R] %s #%s harvested 50%% & SL -> %s", p.symbol, p.ticket, new_sl)

            # Runner trailing ratchet (>= +2.20R): lock 65% of peak gain
            if t_key in self.state["t2_done"] and peak >= sl_dist * 2.20:
                lock_sl = round(p.price_open + peak * 0.65, info.digits) if is_buy else round(p.price_open - peak * 0.65, info.digits)
                if (is_buy and lock_sl > p.sl) or (not is_buy and lock_sl < p.sl):
                    mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": p.ticket, "sl": lock_sl, "tp": p.tp})
                    log.info("[V4.4 RUNNER TRAIL 65%%] %s #%s SL -> %s", p.symbol, p.ticket, lock_sl)

        self._save_state()

    def cycle(self):
        now_utc = datetime.now(timezone.utc)
        acc = mt5.account_info()
        if not acc:
            return
        positions = mt5.positions_get() or []
        orders = mt5.orders_get() or []
        self.manage_positions_and_orders(positions, orders, now_utc)

        my_pos = [p for p in positions if p.magic == MAGIC_NUMBER]
        my_ord = [o for o in orders if o.magic == MAGIC_NUMBER]

        in_news = (now_utc.hour == 13 and 15 <= now_utc.minute <= 45)
        in_killzone = (7 <= now_utc.hour <= 15)

        if now_utc.minute % 15 == 0 and now_utc.minute != self.last_hb_min:
            self.last_hb_min = now_utc.minute
            log.info("[V4.4 M5-VERIFIED HB] %02d:%02d UTC (KZ:%s) | Eq=$%.2f | Pos=%d | Ord=%d",
                     now_utc.hour, now_utc.minute, "ON" if in_killzone else "OFF", acc.equity, len(my_pos), len(my_ord))

        # Variant #4 Gate: 07:00 UTC Killzone open + VPOC non-chop + Vol >= 1.15x
        if now_utc.hour != 7 or in_news:
            return

        for base in PORTFOLIO_6:
            sym = self.resolve_symbol(base)
            if not sym:
                continue
            if any(p.symbol == sym for p in my_pos) or any(o.symbol == sym for o in my_ord):
                continue

            sig = self.compute_verified_signal(sym)
            if not sig or not sig["box_ready"]:
                continue
            if self.state.get("armed_date", {}).get(sym) == sig["today_str"]:
                continue
            if self.state.get("skip_date", {}).get(sym) == sig["today_str"]:
                continue
            if sig["inside_chop"] or sig["vol_ratio"] < 1.15:
                continue

            info = sig["info"]
            tick = mt5.symbol_info_tick(sym)
            if not tick:
                continue

            lot = self.calc_lot(sym, info, acc.equity, sig["sl_dist"])
            pdh_clear = (sig["pdh"] <= sig["buy_stop"]) or ((sig["pdh"] - sig["buy_stop"]) >= sig["sl_dist"] * 0.90)
            pdl_clear = (sig["pdl"] >= sig["sell_stop"]) or ((sig["sell_stop"] - sig["pdl"]) >= sig["sl_dist"] * 0.90)

            if sig["h1_bull"] and tick.ask < sig["buy_stop"] and pdh_clear:
                sl_buy = round(sig["buy_stop"] - sig["sl_dist"], info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_PENDING, "symbol": sym, "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY_STOP, "price": sig["buy_stop"], "sl": sl_buy,
                    "deviation": 20, "magic": MAGIC_NUMBER, "comment": "NEXUS_V44_V4_BUY",
                    "type_time": mt5.ORDER_TIME_DAY, "type_filling": mt5.ORDER_FILLING_IOC,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    self.state.setdefault("armed_date", {})[sym] = sig["today_str"]
                    self._save_state()
                    log.info("[V4.4 VARIANT-4 BUY] %s %.2fL BUY_STOP @ %s | SL=%s | Vol=%.2fx (#%s)",
                             sym, lot, sig["buy_stop"], sl_buy, sig["vol_ratio"], res.order)

            elif sig["h1_bear"] and tick.bid > sig["sell_stop"] and pdl_clear:
                sl_sell = round(sig["sell_stop"] + sig["sl_dist"], info.digits)
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_PENDING, "symbol": sym, "volume": lot,
                    "type": mt5.ORDER_TYPE_SELL_STOP, "price": sig["sell_stop"], "sl": sl_sell,
                    "deviation": 20, "magic": MAGIC_NUMBER, "comment": "NEXUS_V44_V4_SELL",
                    "type_time": mt5.ORDER_TIME_DAY, "type_filling": mt5.ORDER_FILLING_IOC,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    self.state.setdefault("armed_date", {})[sym] = sig["today_str"]
                    self._save_state()
                    log.info("[V4.4 VARIANT-4 SELL] %s %.2fL SELL_STOP @ %s | SL=%s | Vol=%.2fx (#%s)",
                             sym, lot, sig["sell_stop"], sl_sell, sig["vol_ratio"], res.order)

    def run(self):
        log.info("====================================================================================")
        log.info("NEXUS V4.4 M5-VERIFIED VARIANT #4 READY (1.72 TRUE M5 PF | VPOC + VOL>=1.15 + T1/T2)")
        log.info("====================================================================================")
        if not self.connect():
            sys.exit(1)
        try:
            while True:
                self.cycle()
                time.sleep(15)
        except KeyboardInterrupt:
            log.info("Shutdown requested.")
        finally:
            mt5.shutdown()


if __name__ == "__main__":
    NexusV44M5VerifiedEngine().run()
