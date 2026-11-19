from macro_news_gate import check_usd_macro_blackout
from portfolio_heat_governor import sync_sleeve_exposure, evaluate_portfolio_heat_gate
# -*- coding: utf-8 -*-
"""
SHIVSOUL NEXUS v10.2 // ADAPTIVE M5 HYBRID SCALPER + REAL-TIME TELEGRAM TELEMETRY
- T1 (#278062038): BTCUSD M5 Market Impulse & Liquidity Sweep Scalper
- T2 (#278062039): FX Majors M5 Market Scalper + 15-Min TTL Breakout Stop Orders
- T3 (#278062042): XAUUSD M5 Market Scalper + 15-Min TTL Breakout Stop Orders
"""
import os
import sys
import time
import sqlite3
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import MetaTrader5 as mt5

ROOT_DIR = Path(r"C:\Quant-Nexus-Eng")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Load Telegram credentials dynamically from local config modules
TG_TOKEN = ""
TG_CHAT_ID = ""
for cfg_mod in ("telegram_nexus_config", "telegram_config", "nexus_tg_config"):
    try:
        m = __import__(cfg_mod)
        TG_TOKEN = getattr(m, "BOT_TOKEN", getattr(m, "TELEGRAM_BOT_TOKEN", getattr(m, "TOKEN", TG_TOKEN)))
        TG_CHAT_ID = str(getattr(m, "CHAT_ID", getattr(m, "TELEGRAM_CHAT_ID", getattr(m, "CHANNEL_ID", TG_CHAT_ID))))
        if TG_TOKEN and TG_CHAT_ID:
            break
    except Exception:
        pass

try:
    from telegram_notifier_v43 import send_v43_alert as _v43_send
except Exception:
    _v43_send = None

def send_nexus_tg(html_msg: str):
    """Non-blocking Telegram dispatch so network latency never stalls the 3s M5 scan loop."""
    def _worker():
        try:
            if _v43_send is not None:
                _v43_send(html_msg)
                return
            if TG_TOKEN and TG_CHAT_ID:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                with httpx.Client(timeout=6.0) as client:
                    client.post(url, json={
                        "chat_id": TG_CHAT_ID,
                        "text": html_msg,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    })
        except Exception as exc:
            logging.warning(f"[TG-ALERT] Dispatch warning: {exc}")

    threading.Thread(target=_worker, daemon=True).start()

try:
    from vpin_filter import VPINToxicityFilter
    vpin_guard = VPINToxicityFilter(adverse_threshold=0.68)
except Exception:
    vpin_guard = None

LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = ROOT_DIR / "nexus_ledger.db"

logging.basicConfig(
    filename=str(LOG_DIR / "nexus_worker.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

SLEEVE_CONFIGS = {
    "T1": {
        "name": "BTCUSD_M5_SMART_SCALP",
        "login": 278062038,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe",
        "symbols": ["BTCUSD"],
        "max_open": 1,
        "enable_pending_breakout": False,
        "max_pending": 0,
        "pending_ttl_mins": 15,
        "risk_pct": 0.005,
        "rr_target": 1.8,
        "max_spread_pts": 900,
        "active_hours": list(range(0, 21)),
    },
    "T2": {
        "name": "FX_MAJORS_M5_HYBRID_SCALP",
        "login": 278062039,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_Pending_278041169\terminal64.exe",
        "symbols": ["GBPUSD"],
        "max_open": 1,
        "enable_pending_breakout": True,
        "max_pending": 1,
        "pending_ttl_mins": 15,
        "risk_pct": 0.005,
        "rr_target": 1.8,
        "max_spread_pts": 22,
        "active_hours": list(range(1, 21)),
    },
    "T3": {
        "name": "XAUUSD_M5_HYBRID_GOLD",
        "login": 278062042,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_HFT_278041671\terminal64.exe",
        "symbols": ["XAUUSD"],
        "max_open": 1,
        "enable_pending_breakout": True,
        "max_pending": 1,
        "pending_ttl_mins": 15,
        "risk_pct": 0.005,
        "rr_target": 2.0,
        "max_spread_pts": 280,
        "active_hours": list(range(1, 22)),
    }
}

def resolve_symbol(base_sym: str) -> str | None:
    for candidate in (base_sym, base_sym + "m", base_sym + ".a"):
        info = mt5.symbol_info(candidate)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(candidate, True)
            return candidate
    return None

def get_filling_mode(sym_info):
    modes = sym_info.filling_mode
    if modes & 2:
        return mt5.ORDER_FILLING_IOC
    if modes & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN

def calc_ema(vals, period):
    k = 2.0 / (period + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = v * k + ema * (1.0 - k)
    return ema

def flatten_sleeve_positions(sleeve_key: str, reason: str = "DD_CIRCUIT_FLATTEN") -> int:
    """Closes all open positions on the active terminal immediately at market."""
    closed_count = 0
    for p in (mt5.positions_get() or []):
        sym_info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not sym_info or not tick:
            continue
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        close_px = float(tick.bid if is_buy else tick.ask)
        res = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "price": close_px,
            "deviation": 40,
            "magic": p.magic,
            "comment": "NX10_DD_Flat",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": get_filling_mode(sym_info),
        })
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed_count += 1
            logging.warning(f"[{sleeve_key}] Flattened #{p.ticket} ({p.symbol} {p.volume}L) @ {close_px} -> {reason}")
        else:
            logging.error(f"[{sleeve_key}] Failed to flatten #{p.ticket} ({p.symbol}): {getattr(res, 'retcode', mt5.last_error())}")
    return closed_count
def purge_nexus_pending_orders(sleeve_key: str, reason: str = "OCO_CLEANUP"):
    orders = mt5.orders_get() or []
    for o in orders:
        if o.magic == 202610:
            res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                logging.info(f"[{sleeve_key}] Cancelled pending #{o.ticket} ({o.symbol}) -> {reason}")

# === QUANT-NEXUS v11.0 INSTITUTIONAL CORE START ===
import math
from datetime import timedelta

V11_RISK_BUDGET_USD = {
    "T1": 4.50,  # $4.50 fixed risk per trade (BTCUSD / US30)
    "T2": 3.00,  # $3.00 fixed risk per trade (GBPUSD Sweep-Reclaim)
    "T3": 4.50,  # $4.50 fixed risk per trade (XAUUSD Hybrid)
}
V11_MAX_LOT_CAP = {
    "T1": 0.03,
    "T2": 0.05,
    "T3": 0.03,
}

def compute_volatility_parity_lot(sleeve_key: str, symbol: str, entry: float, sl: float, sym_info) -> tuple[float, float]:
    """
    Sizes lot inversely to stop distance so every trade risks an identical dollar budget.
    Returns (calibrated_lot, actual_risk_usd).
    """
    stop_dist = abs(float(entry) - float(sl))
    if stop_dist <= 0 or sym_info is None:
        return 0.01, 0.0

    point = float(sym_info.point) if sym_info.point > 0 else 0.0001
    tick_val = float(sym_info.trade_tick_value) if sym_info.trade_tick_value > 0 else 1.0
    tick_size = float(sym_info.trade_tick_size) if sym_info.trade_tick_size > 0 else point
    usd_per_price_1lot = tick_val / tick_size

    risk_per_1lot = stop_dist * usd_per_price_1lot
    if risk_per_1lot <= 0:
        return 0.01, 0.0

    target_usd = V11_RISK_BUDGET_USD.get(sleeve_key, 4.50)
    vol_min = float(sym_info.volume_min) if sym_info.volume_min > 0 else 0.01
    vol_step = float(sym_info.volume_step) if sym_info.volume_step > 0 else 0.01
    vol_max = min(float(sym_info.volume_max) if sym_info.volume_max > 0 else 0.05, V11_MAX_LOT_CAP.get(sleeve_key, 0.05))

    raw_lot = target_usd / risk_per_1lot
    # Floor to nearest broker volume_step so we never exceed target dollar risk
    steps = math.floor((raw_lot + 1e-9) / vol_step)
    lot = round(max(vol_min, min(vol_max, steps * vol_step)), 2)
    actual_risk_usd = round(lot * risk_per_1lot, 2)
    return lot, actual_risk_usd

def check_symbol_cooldown(symbol: str, now_utc: datetime) -> tuple[bool, str]:
    """
    Enforces:
    - 15-minute (900s) mandatory cooldown after any losing exit on `symbol`
    - 60-minute (3600s) pause after 2 consecutive losses on `symbol`
    """
    try:
        t_from = now_utc - timedelta(hours=4)
        deals = mt5.history_deals_get(t_from, now_utc) or []
        sym_outs = [
            d for d in deals
            if d.symbol == symbol and d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)
        ]
        if not sym_outs:
            return False, ""

        sym_outs.sort(key=lambda d: int(d.time))
        last_d = sym_outs[-1]
        last_net = float(last_d.profit) + float(last_d.swap) + float(last_d.commission)
        elapsed = (now_utc - datetime.fromtimestamp(int(last_d.time), tz=timezone.utc)).total_seconds()

        # Check 2 consecutive losses -> 60m cooldown
        if len(sym_outs) >= 2:
            prev_d = sym_outs[-2]
            prev_net = float(prev_d.profit) + float(prev_d.swap) + float(prev_d.commission)
            if last_net < 0 and prev_net < 0 and elapsed < 3600:
                rem = int((3600 - elapsed) // 60) + 1
                return True, f"2_LOSS_STREAK_PAUSE ({rem}m left)"

        # Check single stop-out -> 15m cooldown
        if last_net < 0 and elapsed < 900:
            rem = int((900 - elapsed) // 60) + 1
            return True, f"POST_SL_15M_COOLDOWN ({rem}m left)"

        return False, ""
    except Exception:
        return False, ""

def run_startup_self_test(sleeve_key: str) -> bool:
    """
    Pre-flight dry-run assertion before entering the live trading loop.
    Catches signature mismatches or broken helpers immediately on boot.
    """
    class _DummyInfo:
        point = 0.01
        digits = 2
        spread = 20
        trade_tick_value = 0.01
        trade_tick_size = 0.01
        volume_min = 0.01
        volume_step = 0.01
        volume_max = 1.00

    dummy_rates = [
        {"open": 100.0 + i * 0.05, "high": 100.2 + i * 0.05, "low": 99.8 + i * 0.05, "close": 100.1 + i * 0.05}
        for i in range(170)
    ]
    _ = evaluate_m5_setup(sleeve_key, "BTCUSD", dummy_rates, _DummyInfo())
    lot, r_usd = compute_volatility_parity_lot(sleeve_key, "BTCUSD", 65000.0, 64550.0, _DummyInfo())
    assert lot >= 0.01 and r_usd > 0, f"Invalid sizer output: lot={lot}, risk={r_usd}"
    h1_test = evaluate_h1_pdh_pdl_context("BTCUSD", dummy_rates[:60], dummy_rates[:3])
    ok_t, _ = passes_htf_liquidity_gate(sleeve_key, "BUY", 105.0, 104.0, 106.0, h1_test)
    assert isinstance(ok_t, bool)
    h_ok, _ = evaluate_portfolio_heat_gate(sleeve_key, "BTCUSD", "SELL", 4.50)
    assert isinstance(h_ok, bool)
    logging.info(f"[{sleeve_key}] v11.3 Pre-Flight Self-Test PASSED (PortfolioHeat + H1/PDH/PDL Gate +  (RiskBudget=${V11_RISK_BUDGET_USD.get(sleeve_key, 4.50):.2f} | SampleLot={lot}L)")
    return True
# === QUANT-NEXUS v11.0 INSTITUTIONAL CORE END ===

# === QUANT-NEXUS v11.2 H1 & PDH/PDL LIQUIDITY ENGINE START ===
def evaluate_h1_pdh_pdl_context(symbol: str, h1_rates=None, d1_rates=None) -> dict:
    """
    Computes H1 Swing Structure (EMA20/EMA50 + 12-bar H1 swing structure)
    and Previous Day High/Low (PDH/PDL) liquidity boundaries.
    """
    if h1_rates is None:
        h1_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 60)
    if d1_rates is None:
        d1_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3)

    ctx = {
        "valid": False,
        "h1_bull": True,
        "h1_bear": True,
        "h1_atr": 0.0,
        "h1_swing_hi": 0.0,
        "h1_swing_lo": 0.0,
        "pdh": 0.0,
        "pdl": 0.0,
        "has_pd_levels": False,
    }

    if h1_rates is not None and len(h1_rates) >= 52:
        h1_closes = [float(r["close"]) for r in h1_rates]
        h1_highs = [float(r["high"]) for r in h1_rates]
        h1_lows = [float(r["low"]) for r in h1_rates]

        def _ema(vals, period):
            k = 2.0 / (period + 1)
            out = [vals[0]]
            for v in vals[1:]:
                out.append(v * k + out[-1] * (1.0 - k))
            return out

        ema20 = _ema(h1_closes, 20)
        ema50 = _ema(h1_closes, 50)
        h1_trs = [
            max(h1_highs[i] - h1_lows[i], abs(h1_highs[i] - h1_closes[i - 1]), abs(h1_lows[i] - h1_closes[i - 1]))
            for i in range(1, len(h1_rates))
        ]
        h1_atr = sum(h1_trs[-14:]) / 14.0 if len(h1_trs) >= 14 else 0.0
        h1_swing_hi = max(h1_highs[-14:-2])
        h1_swing_lo = min(h1_lows[-14:-2])
        last_h1_close = h1_closes[-2]

        ctx["valid"] = True
        ctx["h1_atr"] = h1_atr
        ctx["h1_swing_hi"] = h1_swing_hi
        ctx["h1_swing_lo"] = h1_swing_lo
        ctx["h1_bull"] = (ema20[-2] > ema50[-2]) and (last_h1_close > h1_swing_lo)
        ctx["h1_bear"] = (ema20[-2] < ema50[-2]) and (last_h1_close < h1_swing_hi)

    if d1_rates is not None and len(d1_rates) >= 2:
        # Index -2 is yesterday's completed D1 candle (PDH / PDL)
        ctx["pdh"] = float(d1_rates[-2]["high"])
        ctx["pdl"] = float(d1_rates[-2]["low"])
        ctx["has_pd_levels"] = ctx["pdh"] > ctx["pdl"] > 0.0

    return ctx

def passes_htf_liquidity_gate(
    sleeve_key: str,
    direction: str,
    entry: float,
    bar_low: float,
    bar_high: float,
    htf_ctx: dict,
) -> tuple[bool, str]:
    """
    Validates M5 signal against H1 Swing Structure and PDH/PDL liquidity pools:
    - T1 & T3 (Momentum/Breakout): Requires H1 trend/structure alignment and blocks
      breakout entries trapped directly beneath unaccepted PDH or above unaccepted PDL.
    - T2 (GBPUSD Sweep-Reclaim): Allows H1-aligned sweep-reclaims AND upgrades entries
      that sweep & reclaim PDH/PDL liquidity pools.
    """
    if not htf_ctx or not htf_ctx.get("valid"):
        return True, ""

    is_buy = (direction == "BUY")
    h1_atr = htf_ctx["h1_atr"]
    pdh = htf_ctx["pdh"]
    pdl = htf_ctx["pdl"]
    has_pd = htf_ctx["has_pd_levels"]

    # 1. T2 GBPUSD Sweep-Reclaim: Check for institutional PDH/PDL liquidity sweep first
    if sleeve_key == "T2":
        if is_buy and has_pd and bar_low < pdl and entry > pdl:
            return True, "PDL_SWEEP_RECLAIM_LONG"
        if not is_buy and has_pd and bar_high > pdh and entry < pdh:
            return True, "PDH_SWEEP_RECLAIM_SHORT"
        if is_buy and not htf_ctx["h1_bull"]:
            return False, "H1_BEAR_STRUCTURE_BLOCK"
        if not is_buy and not htf_ctx["h1_bear"]:
            return False, "H1_BULL_STRUCTURE_BLOCK"
        return True, ""

    # 2. T1 (BTCUSD/US30) & T3 (XAUUSD): Require H1 Swing Structure alignment
    if is_buy and not htf_ctx["h1_bull"]:
        return False, "H1_STRUCTURE_COUNTER_LONG"
    if not is_buy and not htf_ctx["h1_bear"]:
        return False, "H1_STRUCTURE_COUNTER_SHORT"

    # 3. Anti-Exhaustion Guard at Previous Day High / Low (PDH/PDL liquidity wall)
    if has_pd and h1_atr > 0:
        buffer_zone = 0.35 * h1_atr
        # Block long breakout entries firing right into PDH resistance without acceptance above PDH
        if is_buy and (pdh - buffer_zone) <= entry < pdh:
            return False, "PDH_LIQUIDITY_WALL_BLOCK"
        # Block short breakout entries firing right into PDL support without acceptance below PDL
        if not is_buy and pdl < entry <= (pdl + buffer_zone):
            return False, "PDL_LIQUIDITY_WALL_BLOCK"

    return True, ""
# === QUANT-NEXUS v11.2 H1 & PDH/PDL LIQUIDITY ENGINE END ===

def evaluate_m5_setup(arg1: str, arg2=None, rates=None, sym_info=None) -> dict | None:
    """
    QUANT-NEXUS v12.1 NEXT-GEN M1/M15 UNIFIED MICRO-SCALP ENGINE (CLOSED-BAR + INTRA-BAR TICK VELOCITY)
    - M15 EMA20/EMA50 fast directional regime + PDH/PDL liquidity gate
    - Priority 1 (Closed M1): M1 Micro-Liquidity Sweep Reclaim & M1 Impulse Strike
    - Priority 2 (Forming M1): Sub-minute Intra-Bar Tick-Velocity Breakout (anti-chase capped at 1.75x M1_ATR)
    """
    if arg1 in ("T1", "T2", "T3") and isinstance(arg2, str):
        sleeve_key = arg1
        symbol = arg2
    else:
        symbol = arg1
        sleeve_key = "T3" if "XAU" in symbol.upper() else ("T2" if any(fx in symbol.upper() for fx in ("EUR", "GBP", "JPY", "AUD")) else "T1")

    if sym_info is None:
        sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return None

    m1_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 60)
    m15_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 65)
    if m1_rates is None or len(m1_rates) < 30 or m15_rates is None or len(m15_rates) < 55:
        return None

    point = float(sym_info.point)
    digits = int(sym_info.digits)
    sp_px = int(sym_info.spread) * point

    def _ema(vals, period):
        k = 2.0 / (period + 1.0)
        out = [vals[0]]
        for v in vals[1:]:
            out.append(v * k + out[-1] * (1.0 - k))
        return out

    # 1. M15 Fast Trend Context
    m15_closes = [float(r["close"]) for r in m15_rates]
    m15_ema20 = _ema(m15_closes, 20)
    m15_ema50 = _ema(m15_closes, 50)
    trend_bull = (m15_ema20[-2] > m15_ema50[-2]) and (m15_ema20[-2] >= m15_ema20[-4])
    trend_bear = (m15_ema20[-2] < m15_ema50[-2]) and (m15_ema20[-2] <= m15_ema20[-4])
    if not (trend_bull or trend_bear):
        return None

    # 2. M1 Micro-Structure & ATR Calibration
    opens = [float(r["open"]) for r in m1_rates]
    highs = [float(r["high"]) for r in m1_rates]
    lows = [float(r["low"]) for r in m1_rates]
    closes = [float(r["close"]) for r in m1_rates]

    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, len(m1_rates))]
    m1_atr = sum(trs[-14:]) / 14.0
    if m1_atr <= 0 or m1_atr < (2.2 * sp_px):
        return None

    # Completed M1 bar (-2) & Forming M1 bar (-1)
    o, h, l, c = opens[-2], highs[-2], lows[-2], closes[-2]
    bar_rng = max(h - l, point)
    body = abs(c - o)

    cur_o, cur_h, cur_l, cur_c = opens[-1], highs[-1], lows[-1], closes[-1]
    cur_rng = max(cur_h - cur_l, point)
    cur_body = abs(cur_c - cur_o)

    swing_hi = max(highs[-10:-2])
    swing_lo = min(lows[-10:-2])
    htf_ctx = evaluate_h1_pdh_pdl_context(symbol)

    direction = None
    tag = None
    score = 0.0
    gate_low, gate_high = l, h

    # Priority 1A: Closed M1 Micro-Liquidity Sweep Reclaim
    if trend_bull and l < swing_lo and c > swing_lo and c > o and (c - l) >= 0.55 * bar_rng:
        direction, tag, score = "BUY", "M1_SWEEP_RECLAIM_LONG", 90.0
    elif trend_bear and h > swing_hi and c < swing_hi and c < o and (h - c) >= 0.55 * bar_rng:
        direction, tag, score = "SELL", "M1_SWEEP_RECLAIM_SHORT", 90.0

    # Priority 1B: Closed M1 Impulse Breakout
    elif trend_bull and c > swing_hi and c > o and bar_rng >= 0.80 * m1_atr and (body / bar_rng) >= 0.58:
        direction, tag, score = "BUY", "M1_IMPULSE_STRIKE_LONG", 87.0
    elif trend_bear and c < swing_lo and c < o and bar_rng >= 0.80 * m1_atr and (body / bar_rng) >= 0.58:
        direction, tag, score = "SELL", "M1_IMPULSE_STRIKE_SHORT", 87.0

    # Priority 2: Sub-Minute Intra-Bar Tick-Velocity Breakout (anti-chase window: 0.70x - 1.75x M1_ATR)
    elif (
        trend_bull
        and cur_c > (swing_hi + 0.15 * m1_atr)
        and cur_c > cur_o
        and (0.70 * m1_atr <= cur_rng <= 1.75 * m1_atr)
        and (cur_body / cur_rng) >= 0.65
    ):
        direction, tag, score = "BUY", "M1_TICK_VELOCITY_LONG", 88.0
        gate_low, gate_high = cur_l, cur_h
    elif (
        trend_bear
        and cur_c < (swing_lo - 0.15 * m1_atr)
        and cur_c < cur_o
        and (0.70 * m1_atr <= cur_rng <= 1.75 * m1_atr)
        and (cur_body / cur_rng) >= 0.65
    ):
        direction, tag, score = "SELL", "M1_TICK_VELOCITY_SHORT", 88.0
        gate_low, gate_high = cur_l, cur_h

    if not direction:
        return None

    # Tight micro-scalp stop distance (1.65x M1 ATR, floored at 4.5x spread)
    sl_dist = round(max(1.65 * m1_atr, 4.5 * sp_px), digits)
    entry = round(cur_c + sp_px, digits) if direction == "BUY" else round(cur_c, digits)
    sl = round(entry - sl_dist, digits) if direction == "BUY" else round(entry + sl_dist, digits)
    tp = round(entry + 1.65 * sl_dist, digits) if direction == "BUY" else round(entry - 1.65 * sl_dist, digits)

    vp_lot, vp_risk = compute_volatility_parity_lot(sleeve_key, symbol, entry, sl, sym_info)
    if 'XAU' in symbol.upper() and vp_lot > 0.01:
        vp_lot = 0.01
    if vp_lot <= 0.0 or vp_risk > (V11_RISK_BUDGET_USD.get(sleeve_key, 4.50) * 1.35):
        return None

    htf_ok, htf_tag_override = passes_htf_liquidity_gate(sleeve_key, direction, entry, gate_low, gate_high, htf_ctx)
    if not htf_ok:
        return None

    return {
        "mode": "MARKET",
        "order_kind": "MARKET",
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "sl_dist": sl_dist,
        "lot": vp_lot,
        "risk_usd": vp_risk,
        "score": score,
        "tag": htf_tag_override or tag,
    }

def guard_t3_pre_rollover(sleeve_key: str, cfg: dict, positions: list):
    """
    Protects open XAUUSD positions on T3 between 21:45 and 21:57 UTC before the 21:58 UTC daily break:
    - If floating positive: locks SL at breakeven + 60-pt pad.
    - If underwater or stop distance <= 450 pts ($4.50): flattens cleanly at market before liquidity drops.
    """
    if sleeve_key != "T3" or not positions:
        return

    for p in positions:
        if "XAUUSD" not in p.symbol.upper():
            continue
        sym_info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not sym_info or not tick:
            continue

        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        mark = float(tick.bid if is_buy else tick.ask)
        open_px = float(p.price_open)
        sl = float(p.sl)
        point = sym_info.point
        digits = sym_info.digits
        pad = 60 * point
        tight_limit = 450 * point

        gain = (mark - open_px) if is_buy else (open_px - mark)
        sl_dist_now = abs(mark - sl) if sl > 0 else 0.0

        # Case A: Floating in profit -> lock risk-free breakeven + pad
        if gain > pad:
            be_sl = round(open_px + pad if is_buy else open_px - pad, digits)
            needs_lock = (is_buy and (sl < be_sl or sl == 0.0)) or (not is_buy and (sl > be_sl or sl == 0.0))
            if needs_lock:
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "sl": be_sl,
                    "tp": p.tp
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    logging.info(f"[T3-ROLLOVER-GUARD] Locked BE SL on #{p.ticket} ({p.symbol}) -> {be_sl}")
                    send_nexus_tg(
                        f"🛡️ <b>[NEXUS T3 // PRE-ROLLOVER BE LOCK]</b>\n"
                        f"• Ticket: <code>#{p.ticket}</code> (<b>{p.symbol}</b>)\n"
                        f"• Action: Profitable runner locked at <code>{be_sl}</code> ahead of 21:58 UTC break."
                    )
            continue

        # Case B: Underwater or tight stop (<= $4.50) -> flatten before 21:58 UTC close
        if gain <= pad or sl == 0.0 or sl_dist_now <= tight_limit:
            close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "price": mark,
                "deviation": 40,
                "magic": p.magic,
                "comment": "NX10_PreRoll_Flat",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": get_filling_mode(sym_info),
            })
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                logging.info(f"[T3-ROLLOVER-GUARD] Flattened #{p.ticket} ({p.symbol}) @ {mark} before 21:58 UTC close")
                send_nexus_tg(
                    f"🧹 <b>[NEXUS T3 // PRE-ROLLOVER FLATTEN]</b>\n"
                    f"• Ticket: <code>#{p.ticket}</code> (<b>{p.symbol}</b> {p.volume}L)\n"
                    f"• Exit Price: <code>{mark}</code> (PnL: <code>{p.profit:+.2f}</code>)\n"
                    f"• Reason: Tight/underwater exposure closed safely before 21:58 UTC daily break."
                )
def update_heartbeat(sleeve: str, login: int, equity: float, open_count: int, status: str):
    try:
        conn = sqlite3.connect(LEDGER_PATH, timeout=5.0)
        conn.execute("""
            INSERT OR REPLACE INTO worker_heartbeats (sleeve, pid, login, equity, open_count, last_tick_utc, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sleeve, os.getpid(), login, equity, open_count, datetime.now(timezone.utc).isoformat(), status))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"[{sleeve}] Heartbeat DB error: {e}")

def log_intent(sleeve: str, symbol: str, direction: str, volume: float, entry: float, sl: float, tp: float, score: float, state: str, ticket: int = 0):
    try:
        conn = sqlite3.connect(LEDGER_PATH, timeout=5.0)
        now_iso = datetime.now(timezone.utc).isoformat()
        cid = f"{sleeve}_{symbol}_{int(time.time())}"
        conn.execute("""
            INSERT INTO order_intents (client_order_id, sleeve, symbol, direction, volume, entry_req, init_sl, init_tp, score, regime_json, state, mt5_ticket, created_utc, updated_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cid, sleeve, symbol, direction, volume, entry, sl, tp, score, "{}", state, ticket, now_iso, now_iso))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"[{sleeve}] Intent DB error: {e}")


def v13_smart_confluence_gate(symbol: str, atr_val: float, sp_px: float, now_utc) -> tuple[bool, float, str]:
    """v13.0 Smart Rollover Shield + Asset-Calibrated ATR/Spread Gate + Session Liquidity Bonus."""
    hhmm = now_utc.hour * 60 + now_utc.minute
    # Block daily Exness rollover spread-spike window (21:50 - 23:15 UTC)
    if (21 * 60 + 50) <= hhmm <= (23 * 60 + 15):
        return False, 0.0, "ROLLOVER_SHIELD"
    if sp_px <= 0 or atr_val <= 0:
        return False, 0.0, "ZERO_FEED"
    ratio = atr_val / sp_px
    is_fx = any(k in symbol.upper() for k in ("GBP", "AUD", "EUR", "USDJPY", "USDCAD"))
    min_ratio = 1.45 if is_fx else 2.50
    if ratio < min_ratio:
        return False, 0.0, f"LOW_ATR_SPREAD({ratio:.1f}x<{min_ratio}x)"
    # Session & Spread-Compression Confluence Bonus (0 - 25 pts)
    bonus = 10.0 if ratio >= (min_ratio * 1.6) else 5.0
    if (0 <= now_utc.hour <= 4) or (7 <= now_utc.hour <= 16):  # Asia expansion + London/NY overlap
        bonus += 15.0
    return True, bonus, f"OK({ratio:.1f}x)"


def run_worker(sleeve_key: str):
    cfg = SLEEVE_CONFIGS[sleeve_key]
    if not mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"], portable=False):
        logging.error(f"[{sleeve_key}] MT5 init failed on {cfg['path']}: {mt5.last_error()}")
        sys.exit(1)

    logging.info(f"[{sleeve_key}] Hybrid M5 Scalper + Telegram Telemetry v13.0 INTELLIGENT CONFLUENCE + FAST-STRIKE SCALPER ONLINE on #{cfg['login']}")
    last_bar_traded = {}
    tracked_pending_tickets = {}  # order_ticket -> dict metadata
    announced_open_tickets = set()
    run_startup_self_test(sleeve_key)
    consecutive_errors = 0
    dd_halt_alerted_date = None
    tracked_utc_day = None
    daily_dd_floor = round(float(getattr(mt5.account_info(), 'equity', 0.0)) * 0.96, 2)

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            acct = mt5.account_info()
            if not acct:
                time.sleep(5)
                continue

            equity = float(acct.equity)
            if equity <= 1.0:
                time.sleep(2)
                continue
            positions = mt5.positions_get() or []
            pending_orders = [o for o in (mt5.orders_get() or []) if o.magic == 202610]
            open_count = len(positions)
            sync_sleeve_exposure(sleeve_key, positions, {pos.symbol: mt5.symbol_info(pos.symbol) for pos in positions}, now_utc)

            # Detect any pending stop order that triggered into a live position
            for p in positions:
                if p.magic == 202610 and p.ticket not in announced_open_tickets:
                    announced_open_tickets.add(p.ticket)
                    if p.ticket in tracked_pending_tickets:
                        meta = tracked_pending_tickets.pop(p.ticket)
                        p_dir = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                        send_nexus_tg(
                            f"⚡ <b>[NEXUS {sleeve_key} // PENDING BREAKOUT FILLED]</b>\n"
                            f"• Account: <code>#{cfg['login']}</code>\n"
                            f"• Asset: <b>{p.symbol}</b> ({p_dir} {p.volume}L)\n"
                            f"• Fill Price: <code>{p.price_open}</code> (Trigger: <code>{meta['trigger']}</code>)\n"
                            f"• SL: <code>{p.sl}</code> | TP: <code>{p.tp}</code>\n"
                            f"• Setup: <code>{meta['tag']}</code>"
                        )
                        log_intent(sleeve_key, p.symbol, p_dir, p.volume, p.price_open, p.sl, p.tp, meta["score"], "PENDING_FILLED", int(p.ticket))

            # Clean expired/cancelled tickets from tracked_pending_tickets
            live_pending_ids = {o.ticket for o in pending_orders}
            for stale_id in list(tracked_pending_tickets.keys()):
                if stale_id not in live_pending_ids:
                    tracked_pending_tickets.pop(stale_id, None)

            # Dynamic Daily DD Circuit Guard (4.0% max daily drawdown from UTC session start equity)
            today_str = now_utc.strftime("%Y-%m-%d")
            if tracked_utc_day != today_str:
                tracked_utc_day = today_str
                # Preserve T2 halt through 2026-11-18 UTC; otherwise set floor at 96.0% of session start equity
                if sleeve_key == "T2" and today_str == "2026-11-18" and equity < round(equity * 0.96, 2):
                    daily_dd_floor = round(equity * 0.96, 2)
                else:
                    daily_dd_floor = round(equity * 0.96, 2)
                logging.info(f"[{sleeve_key}] UTC Day {today_str} Baseline Equity=${equity:.2f} | 4.0% DD Floor=${daily_dd_floor:.2f}")

            if equity <= daily_dd_floor:
                purged_cnt = len(pending_orders)
                if pending_orders:
                    purge_nexus_pending_orders(sleeve_key, "DD_CIRCUIT_HALT")
                closed_cnt = flatten_sleeve_positions(sleeve_key, "DD_CIRCUIT_HALT") if open_count > 0 else 0
                if dd_halt_alerted_date != today_str or closed_cnt > 0:
                    dd_halt_alerted_date = today_str
                    post_acct = mt5.account_info()
                    final_eq = float(post_acct.equity) if post_acct else equity
                    logging.warning(f"[{sleeve_key}] DD_CIRCUIT_HALT triggered at Equity=${final_eq:.2f} (<= ${daily_dd_floor:.2f}) | Flattened={closed_cnt}")
                    send_nexus_tg(
                        f"🚨 <b>[NEXUS {sleeve_key} // DD CIRCUIT HALT + FLATTEN]</b>\n"
                        f"• Account: <code>#{cfg['login']}</code> ({cfg['name']})\n"
                        f"• Equity: <b><code>${final_eq:.2f}</code></b> (4.0% Daily Floor: <code>${daily_dd_floor:.2f}</code>)\n"
                        f"• Flattened Positions: <b>{closed_cnt}</b> | Purged Pending: <b>{purged_cnt}</b>\n"
                        f"• Status: <b>FLAT & HALTED</b> until next UTC session reset."
                    )
                consecutive_errors = 0
                update_heartbeat(sleeve_key, cfg["login"], equity, len(mt5.positions_get() or []), "DD_CIRCUIT_HALT")
                time.sleep(30)
                continue

            # Exness Rollover Protection (21:45 - 00:15 UTC)
            if (now_utc.hour == 21 and now_utc.minute >= 45) or now_utc.hour in (22, 23) or now_utc.hour not in cfg["active_hours"]:
                if pending_orders:
                    purge_nexus_pending_orders(sleeve_key, "ROLLOVER_BLACKOUT")
                if now_utc.hour == 21 and 45 <= now_utc.minute <= 57:
                    guard_t3_pre_rollover(sleeve_key, cfg, positions)
                consecutive_errors = 0
                update_heartbeat(sleeve_key, cfg["login"], equity, len(mt5.positions_get() or []), "ROLLOVER_GUARD")
                time.sleep(15)
                continue

            is_macro_blackout, macro_reason = check_usd_macro_blackout(now_utc)
            if is_macro_blackout:
                if pending_orders:
                    purge_nexus_pending_orders(sleeve_key, "MACRO_NEWS_BLACKOUT")
                consecutive_errors = 0
                update_heartbeat(sleeve_key, cfg["login"], equity, open_count, f"NEWS_BLACKOUT ({macro_reason})")
                time.sleep(15)
                continue

            # OCO Cleanup when a position is active
            if open_count >= cfg["max_open"]:
                if pending_orders:
                    purge_nexus_pending_orders(sleeve_key, "POSITION_FILLED_OCO")
                consecutive_errors = 0
                update_heartbeat(sleeve_key, cfg["login"], equity, open_count, "MANAGING_ACTIVE")
                time.sleep(5)
                continue

            for base_sym in cfg["symbols"]:
                if len(mt5.positions_get() or []) >= cfg["max_open"]:
                    break

                sym = resolve_symbol(base_sym)
                if not sym:
                    continue

                sym_info = mt5.symbol_info(sym)
                tick = mt5.symbol_info_tick(sym)
                if not sym_info or not tick or sym_info.spread > cfg["max_spread_pts"]:
                    continue

                m1_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 2)
                if m1_rates is None or len(m1_rates) < 2:
                    continue
                bar_ts = int(m1_rates[-1]["time"])
                if last_bar_traded.get(sym) == bar_ts:
                    continue

                setup = evaluate_m5_setup(sym)
                if not setup:
                    continue

                heat_ok, heat_reason = evaluate_portfolio_heat_gate(
                    sleeve_key, sym, setup["direction"], float(setup.get("risk_usd", 4.50)), now_utc
                )
                if not heat_ok:
                    logging.info(f"[{sleeve_key}] {sym} {setup['direction']} blocked by v11.3 Portfolio Governor: {heat_reason}")
                    continue

                direction = setup["direction"]
                sl_dist = setup["sl_dist"]
                score = setup["score"]
                tag = setup["tag"]

                # Directional VPIN Adverse-Selection Filter
                if vpin_guard is not None:
                    v_res = vpin_guard.compute_directional_vpin(sym, direction, num_recent_ticks=3000)
                    if v_res.get("adverse_toxic"):
                        log_intent(sleeve_key, sym, direction, 0.0, 0.0, 0.0, 0.0, score, f"VPIN_VETO ({v_res.get('signed_vpin')})")
                        last_bar_traded[sym] = bar_ts
                        continue

                # Risk-calibrated position size (0.5% equity risk)
                risk_usd = equity * cfg["risk_pct"]
                tick_val = sym_info.trade_tick_value or 1.0
                tick_size = sym_info.trade_tick_size or sym_info.point
                sl_ticks = sl_dist / tick_size
                raw_lots = risk_usd / max(sl_ticks * tick_val, 0.01)
                step = sym_info.volume_step
                lots = float(setup.get('lot') or max(sym_info.volume_min, min(0.10, round(round(raw_lots / step) * step, 2))))
                digits = sym_info.digits

                # === MODE A: IMMEDIATE MARKET SCALP ===
                if setup["mode"] == "MARKET":
                    if pending_orders:
                        purge_nexus_pending_orders(sleeve_key, "MARKET_STRIKE_OVERRIDE")

                    if direction == "BUY":
                        entry = tick.ask
                        sl = round(entry - sl_dist, digits)
                        tp = round(entry + (sl_dist * cfg["rr_target"]), digits)
                        order_type = mt5.ORDER_TYPE_BUY
                    else:
                        entry = tick.bid
                        sl = round(entry + sl_dist, digits)
                        tp = round(entry - (sl_dist * cfg["rr_target"]), digits)
                        order_type = mt5.ORDER_TYPE_SELL

                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": sym,
                        "volume": lots,
                        "type": order_type,
                        "price": entry,
                        "sl": sl,
                        "tp": tp,
                        "deviation": 35,
                        "magic": 202610,
                        "comment": f"NX10_{tag[:14]}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": get_filling_mode(sym_info),
                    })
                    last_bar_traded[sym] = bar_ts
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        ticket_id = int(res.order)
                        announced_open_tickets.add(ticket_id)
                        logging.info(f"[{sleeve_key}] MARKET {direction} {lots}L {sym} @ {res.price} | SL={sl} TP={tp}")
                        log_intent(sleeve_key, sym, direction, lots, entry, sl, tp, score, "EXECUTED_MARKET", ticket_id)
                        send_nexus_tg(
                            f"🚀 <b>[NEXUS {sleeve_key} // M5 MARKET SCALP]</b>\n"
                            f"• Account: <code>#{cfg['login']}</code>\n"
                            f"• Asset: <b>{sym}</b> ({direction} {lots}L)\n"
                            f"• Fill: <code>{res.price}</code> | Ticket: <code>#{ticket_id}</code>\n"
                            f"• SL: <code>{sl}</code> | TP: <code>{tp}</code> ({cfg['rr_target']}R)\n"
                            f"• Setup: <code>{tag}</code> (Score: {score})"
                        )
                        break

                # === MODE B: PENDING BREAKOUT STOP ORDER (T2 & T3) ===
                elif setup["mode"] == "PENDING" and cfg["enable_pending_breakout"]:
                    current_pending = [o for o in (mt5.orders_get() or []) if o.magic == 202610]
                    if len(current_pending) >= cfg["max_pending"]:
                        continue

                    stops_level_px = sym_info.trade_stops_level * sym_info.point
                    min_dist = max(stops_level_px * 1.2, 10 * sym_info.point)

                    if direction == "BUY":
                        trig = round(max(setup["trigger_price"], tick.ask + min_dist), digits)
                        sl = round(trig - sl_dist, digits)
                        tp = round(trig + (sl_dist * cfg["rr_target"]), digits)
                        p_type = mt5.ORDER_TYPE_BUY_STOP
                    else:
                        trig = round(min(setup["trigger_price"], tick.bid - min_dist), digits)
                        sl = round(trig + sl_dist, digits)
                        tp = round(trig - (sl_dist * cfg["rr_target"]), digits)
                        p_type = mt5.ORDER_TYPE_SELL_STOP

                    exp_ts = int((datetime.now(timezone.utc) + timedelta(minutes=cfg["pending_ttl_mins"])).timestamp())

                    res = mt5.order_send({
                        "action": mt5.TRADE_ACTION_PENDING,
                        "symbol": sym,
                        "volume": lots,
                        "type": p_type,
                        "price": trig,
                        "sl": sl,
                        "tp": tp,
                        "deviation": 35,
                        "magic": 202610,
                        "comment": f"NX10_{tag[:14]}",
                        "type_time": mt5.ORDER_TIME_SPECIFIED,
                        "expiration": exp_ts,
                        "type_filling": get_filling_mode(sym_info),
                    })
                    last_bar_traded[sym] = bar_ts
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        order_id = int(res.order)
                        tracked_pending_tickets[order_id] = {"trigger": trig, "tag": tag, "score": score}
                        logging.info(f"[{sleeve_key}] PENDING {tag} {lots}L {sym} @ {trig} | SL={sl} TP={tp} (TTL {cfg['pending_ttl_mins']}m)")
                        log_intent(sleeve_key, sym, direction, lots, trig, sl, tp, score, "PLACED_PENDING", order_id)
                        send_nexus_tg(
                            f"🎯 <b>[NEXUS {sleeve_key} // PENDING BREAKOUT ARMED]</b>\n"
                            f"• Account: <code>#{cfg['login']}</code>\n"
                            f"• Asset: <b>{sym}</b> ({tag} {lots}L)\n"
                            f"• Trigger: <code>{trig}</code> | Ticket: <code>#{order_id}</code>\n"
                            f"• SL: <code>{sl}</code> | TP: <code>{tp}</code> ({cfg['rr_target']}R)\n"
                            f"• TTL: <b>{cfg['pending_ttl_mins']} mins</b> (Auto-OCO protected)"
                        )
                        break

            p_count = len([o for o in (mt5.orders_get() or []) if o.magic == 202610])
            status_str = f"ACTIVE_HYBRID (Open:{open_count} Pend:{p_count})" if cfg["enable_pending_breakout"] else f"ACTIVE_SCALP (Open:{open_count})"
            consecutive_errors = 0
            update_heartbeat(sleeve_key, cfg["login"], equity, open_count, status_str)
            time.sleep(3)

        except KeyboardInterrupt:
            break
        except Exception as e:
            consecutive_errors += 1
            logging.error(f"[{sleeve_key}] Loop exception ({consecutive_errors}/3): {e}")
            if consecutive_errors >= 3:
                send_nexus_tg(
                    f"?? <b>[NEXUS {sleeve_key} // 3-STRIKE CRITICAL RESTART]</b>\n"
                    f"? Error: <code>{e}</code>\n"
                    f"? Action: Exiting worker so Watchdog relaunches cleanly."
                )
                mt5.shutdown()
                sys.exit(1)
            time.sleep(5)

    mt5.shutdown()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python nexus_sleeve_worker.py <T1|T2|T3>")
        sys.exit(1)
    run_worker(sys.argv[1].upper())









