import json
import time
import math
import httpx
import logging
import numpy as np
import MetaTrader5 as mt5
from pathlib import Path
from datetime import datetime, timezone

import telegram_config as tc
from nexus_ship_core import SLEEVES, is_valid_live_tick, evaluate_weekly_circuit_breaker
from kalman_regime_filter import compute_kalman_fair_value, compute_momentum_alpha, compute_ou_mean_reversion

PROJECT_DIR = Path("C:/Quant-Nexus-Eng")
STATE_FILE = PROJECT_DIR / "tripartite_60s_state.json"
LOG_FILE = PROJECT_DIR / "nexus_tripartite_60s_vision.log"
SLIPPAGE_LEDGER = PROJECT_DIR / "execution_slippage_ledger.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("ShivSoulDissolveHUD")

SILO_CONFIG = {
    "T1": {
        "title": "?? SHIVSOUL NEXUS // T1 BTCUSD CRYPTO DESK v6.0",
        "account": 278062038,
        "gate": 82.0,
        "max_score": 98.0,
        "max_positions": 1,
        "utc_hours": list(range(0, 24)),
        "allowed_ict": ("OB+IFVG", "VAL-RECLAIM", "EMA-FLOW"),
        "max_spr_atr": 0.12,
        "risk_pct": 0.0045,
        "max_risk_usd": 5.0,
        "sl_atr_mult": 2.0,
        "tp_r_mult": 2.50,
        "be_trigger_r": 1.10,
        "be_lock_r": 0.15,
        "trail_trigger_r": 1.80,
        "trail_atr_mult": 1.2,
        "max_daily_sleeve_losses": 2,
        "gate_label": "T1(BTC) 82-98% | 24/7 Crypto | 2.0xATR | BE@+1.1R",
        "assets": [
            (["BTCUSDm", "BTCUSD"], "M15"),
        ],
    },
    "T2": {
        "title": "?? SHIVSOUL NEXUS // T2 FX NY-KZ DESK v6.0",
        "account": 278062039,
        "gate": 80.0,
        "max_score": 89.0,
        "max_positions": 2,
        "utc_hours": [13, 14, 15, 16, 17],
        "allowed_ict": ("OB+IFVG", "VAL-RECLAIM"),
        "max_spr_atr": 0.15,
        "risk_pct": 0.0060,
        "max_risk_usd": 6.5,
        "sl_atr_mult": 1.6,
        "tp_r_mult": 2.00,
        "be_trigger_r": 0.90,
        "be_lock_r": 0.12,
        "trail_trigger_r": 1.60,
        "trail_atr_mult": 1.0,
        "max_daily_sleeve_losses": 2,
        "gate_label": "T2(FX) 80-89% | NY 13-17UTC | OB/VAL | CCY-Mutex | BE@+0.9R",
        "assets": [
            (["EURUSDm", "EURUSD"], "M15"),
            (["GBPUSDm", "GBPUSD"], "M15"),
            (["USDJPYm", "USDJPY"], "M15"),
            (["GBPJPYm", "GBPJPY"], "M15"),
            (["AUDUSDm", "AUDUSD"], "M15"),
            (["USDCADm", "USDCAD"], "M15"),
        ],
    },
    "T3": {
        "title": "?? SHIVSOUL NEXUS // T3 XAUUSD BULLION DESK v6.0",
        "account": 278062042,
        "gate": 82.0,
        "max_score": 98.0,
        "max_positions": 1,
        "utc_hours": [13, 14, 15, 16, 17],
        "allowed_ict": ("OB+IFVG", "VAL-RECLAIM"),
        "max_spr_atr": 0.14,
        "risk_pct": 0.0075,
        "max_risk_usd": 8.0,
        "sl_atr_mult": 1.8,
        "tp_r_mult": 2.50,
        "be_trigger_r": 1.15,
        "be_lock_r": 0.15,
        "trail_trigger_r": 1.85,
        "trail_atr_mult": 1.2,
        "max_daily_sleeve_losses": 2,
        "gate_label": "T3(XAU) >= 82% | NY 13-17UTC | $8 ATR-Cap | BE@+1.15R",
        "assets": [
            (["XAUUSDm", "XAUUSD"], "M15"),
        ],
    },
}

BRUSH_AWAY_EVERY_CYCLES = 60
MAGIC_NUMBERS = {"T1": 560101, "T2": 560201, "T3": 560301}

GLOBE_SWEEP = [
    "🌎 ▰▱▱▱▱",
    "🌍 ▰▰▱▱▱",
    "🌏 ▰▰▰▱▱",
    "🌎 ▰▰▰▰▱",
    "🌍 ▰▰▰▰▰",
    "🌏 ▱▰▰▰▰",
    "🌎 ▱▱▰▰▰",
    "🌍 ▱▱▱▰▰",
]


def resolve_symbol(candidates: list[str]) -> str | None:
    for sym in candidates:
        info = mt5.symbol_info(sym)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(sym, True)
            return sym
    return None


def calc_atr14(rates) -> float:
    if rates is None or len(rates) < 16:
        return 0.0
    h, l, c = rates["high"], rates["low"], rates["close"]
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-14:]))


def ema(arr: np.ndarray, span: int) -> float:
    if len(arr) == 0:
        return 0.0
    alpha = 2.0 / (span + 1.0)
    val = float(arr[0])
    for x in arr[1:]:
        val = alpha * float(x) + (1.0 - alpha) * val
    return val


def get_session_globe_tag(now_utc: datetime, cycle_num: int) -> str:
    sweep = GLOBE_SWEEP[cycle_num % len(GLOBE_SWEEP)]
    h, m = now_utc.hour, now_utc.minute
    mins = h * 60 + m
    if (20 * 60 + 55) <= mins <= (22 * 60 + 10):
        sess = "ROLLOVER GUARD"
    elif 0 <= h < 7:
        sess = "🇯🇵 ASIA-TOKYO"
    elif 7 <= h < 12:
        sess = "🇬🇧 LDN-KILLZONE"
    elif 12 <= h < 16:
        sess = "🇺🇸 NY-LDN OVLP"
    elif 16 <= h < 21:
        sess = "🇺🇸 NY-PM SESSION"
    else:
        sess = "🇦🇺 SYD-PREOPEN"
    return f"{sweep} | {sess}"


def manage_open_positions(sleeve: str, positions: list) -> dict[int, str]:
    """
    Enforces terminal-isolated Breakeven Lock and ATR(14) Trailing Stop
    reconstructing true initial 1R from original order SL.
    """
    badges: dict[int, str] = {}
    scfg = SILO_CONFIG[sleeve]
    for p in positions:
        sym = p.symbol
        tick = mt5.symbol_info_tick(sym)
        info = mt5.symbol_info(sym)
        if not is_valid_live_tick(tick) or info is None:
            continue

        r_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 30)
        atr14 = calc_atr14(r_m15)
        if atr14 <= 0:
            atr14 = abs(p.price_open - p.sl) / scfg["sl_atr_mult"] if p.sl > 0 else 0.0
        if atr14 <= 0:
            continue

        is_buy = p.type == 0
        entry = float(p.price_open)
        cur_sl = float(p.sl)
        cur_tp = float(p.tp)
        spot = float(tick.bid if is_buy else tick.ask)
        digits = info.digits
        stops_min = max(info.trade_stops_level, 5) * info.point

        orders_hist = mt5.history_orders_get(position=p.ticket) or []
        init_ord = next((o for o in orders_hist if o.sl > 0), None)
        orig_sl = float(init_ord.sl) if init_ord else cur_sl
        r_dist = abs(entry - orig_sl) if (orig_sl > 0 and ((is_buy and orig_sl < entry) or (not is_buy and orig_sl > entry))) else (atr14 * scfg["sl_atr_mult"])
        if r_dist <= 0:
            r_dist = atr14 * scfg["sl_atr_mult"]

        unrealized_dist = (spot - entry) if is_buy else (entry - spot)
        r_mult = unrealized_dist / r_dist

        new_sl = None
        mode_tag = None

        if r_mult >= scfg["trail_trigger_r"]:
            trail_dist = atr14 * scfg["trail_atr_mult"]
            candidate_sl = round((spot - trail_dist) if is_buy else (spot + trail_dist), digits)
            if is_buy and candidate_sl > cur_sl + (2 * info.point) and (spot - candidate_sl) >= stops_min:
                new_sl = candidate_sl
                mode_tag = f"TRAIL@{r_mult:.1f}R"
            elif (not is_buy) and (cur_sl == 0.0 or candidate_sl < cur_sl - (2 * info.point)) and (candidate_sl - spot) >= stops_min:
                new_sl = candidate_sl
                mode_tag = f"TRAIL@{r_mult:.1f}R"
            else:
                badges[p.ticket] = f"TRAIL-HOLD({r_mult:.1f}R)"
        elif r_mult >= scfg["be_trigger_r"]:
            be_lock = round((entry + r_dist * scfg["be_lock_r"]) if is_buy else (entry - r_dist * scfg["be_lock_r"]), digits)
            if is_buy and cur_sl < be_lock - info.point and (spot - be_lock) >= stops_min:
                new_sl = be_lock
                mode_tag = f"BE+{scfg['be_lock_r']:.2f}R"
            elif (not is_buy) and (cur_sl == 0.0 or cur_sl > be_lock + info.point) and (be_lock - spot) >= stops_min:
                new_sl = be_lock
                mode_tag = f"BE+{scfg['be_lock_r']:.2f}R"
            else:
                badges[p.ticket] = "BE-LOCKED"

        if new_sl is not None:
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": sym,
                "position": p.ticket,
                "sl": new_sl,
                "tp": cur_tp,
            })
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                badges[p.ticket] = mode_tag
                log.info(f"[{sleeve}] {mode_tag} #{p.ticket} ({sym}): SL moved {cur_sl:.{digits}f} -> {new_sl:.{digits}f} (Spot={spot:.{digits}f}, +{r_mult:.2f}R)")
            else:
                log.warning(f"[{sleeve}] SLTP modify rejected #{p.ticket} ({sym}): {res.retcode if res else mt5.last_error()}")

    return badges


def analyze_asset(sym: str, sleeve: str, tf_label: str) -> dict:
    tick = mt5.symbol_info_tick(sym)
    info = mt5.symbol_info(sym)
    clean_name = sym.replace("m", "")
    if not is_valid_live_tick(tick) or info is None:
        return {
            "valid": False,
            "sleeve": sleeve,
            "symbol": clean_name,
            "tf": tf_label,
            "score": 0.0,
            "direction": "FLAT",
            "reason": "CLOSED-FEED",
        }

    r_d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 50)
    r_h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 50)
    r_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50)
    r_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 65)

    if any(r is None or len(r) < 30 for r in (r_d1, r_h4, r_h1, r_m15)):
        return {
            "valid": False,
            "sleeve": sleeve,
            "symbol": clean_name,
            "tf": tf_label,
            "score": 0.0,
            "direction": "FLAT",
            "reason": "WARMING-BARS",
        }

    spot = float(tick.bid)
    atr14 = calc_atr14(r_m15)
    spread_price = max(0.0, float(tick.ask - tick.bid))
    spr_atr = (spread_price / atr14) if atr14 > 0 else 999.0


    # 1. Top-Down 4-Timeframe Alignment (D1, H4, H1, M15)
    d1_dir = 1 if r_d1["close"][-1] > ema(r_d1["close"], 20) else -1
    h4_dir = 1 if r_h4["close"][-1] > ema(r_h4["close"], 20) else -1
    h1_dir = 1 if r_h1["close"][-1] > ema(r_h1["close"], 20) else -1
    m15_dir = 1 if r_m15["close"][-1] > ema(r_m15["close"], 20) else -1

    htf_sum = d1_dir + h4_dir + h1_dir
    if htf_sum >= 2 and m15_dir == 1:
        direction = "BUY"
        dir_sign = 1
    elif htf_sum <= -2 and m15_dir == -1:
        direction = "SELL"
        dir_sign = -1
    else:
        direction = "FLAT"
        dir_sign = 0

    trend_code = f"D1{'+' if d1_dir>0 else '-'}H4{'+' if h4_dir>0 else '-'}H1{'+' if h1_dir>0 else '-'}M15{'+' if m15_dir>0 else '-'}"

    # 2. Institutional S/R Liquidity Dealing Range (SSL Support vs BSL Resistance)
    bsl_res = max(float(np.max(r_m15["high"][-48:])), float(np.max(r_h1["high"][-24:])))
    ssl_sup = min(float(np.min(r_m15["low"][-48:])), float(np.min(r_h1["low"][-24:])))
    rng = max(bsl_res - ssl_sup, 1e-9)
    rng_pct = min(100.0, max(0.0, ((spot - ssl_sup) / rng) * 100.0))
    zone_tag = f"PREM-{rng_pct:.0f}%" if rng_pct >= 65.0 else (f"DISC-{rng_pct:.0f}%" if rng_pct <= 35.0 else f"EQ-{rng_pct:.0f}%")

    # 3. Tick-Delta, Directional Imbalance Index (DII), and tVPIN
    closes = r_m15["close"][-12:]
    opens = r_m15["open"][-12:]
    highs = r_m15["high"][-12:]
    lows = r_m15["low"][-12:]
    vols = r_m15["tick_volume"][-12:].astype(float)

    bar_span = np.maximum(highs - lows, 1e-9)
    signed_delta = ((closes - opens) / bar_span) * vols
    net_delta_pts = int(round(float(np.sum(signed_delta))))
    dii = float(np.sum(signed_delta) / max(np.sum(vols), 1.0))
    tvpin = float(np.mean(np.abs(signed_delta) / np.maximum(vols, 1.0)))

    # 4. ICT & Momentum Structure Tag (OB+IFVG / VAL-RECLAIM / EMA-FLOW / NEUTRAL)
    c0, c1 = r_m15["close"][-4], r_m15["close"][-3]
    h0, l0 = r_m15["high"][-4], r_m15["low"][-4]
    h2, l2 = r_m15["high"][-2], r_m15["low"][-2]
    bull_fvg = l2 > h0 and c1 > c0
    bear_fvg = h2 < l0 and c1 < c0
    fvg_match = (dir_sign == 1 and bull_fvg) or (dir_sign == -1 and bear_fvg)
    ema9 = ema(r_m15["close"][-25:], 9)
    ema21 = ema(r_m15["close"][-35:], 21)
    ema_stack = (dir_sign == 1 and spot > ema9 > ema21) or (dir_sign == -1 and spot < ema9 < ema21)

    if fvg_match:
        ict_tag = "OB+IFVG"
    elif (dir_sign == 1 and rng_pct <= 38.0) or (dir_sign == -1 and rng_pct >= 62.0):
        ict_tag = "VAL-RECLAIM"
    elif ema_stack:
        ict_tag = "EMA-FLOW"
    else:
        ict_tag = "NEUTRAL"

    mom = compute_momentum_alpha(closes=np.asarray(r_m15['close'], dtype=float), atr14=atr14, sleeve=sleeve)
    kf = compute_kalman_fair_value(
        closes=np.asarray(r_m15["close"], dtype=float),
        atr14=atr14,
        sleeve=sleeve,
        utc_hour=datetime.now(timezone.utc).hour,
        spread_price=spread_price,
        tvpin=float(tvpin),
    )
    ou = compute_ou_mean_reversion(
        closes=np.asarray(r_m15['close'], dtype=float),
        fair_value=float(kf.get("fair_value", float(np.asarray(r_m15['close'], dtype=float)[-1]))),
        atr14=atr14,
        lookback=64,
    )

    # 5. Calibrated 4-TF + Institutional Flow + Cronus ML Composite Score
    efficiency = abs(float(r_m15["close"][-1] - r_m15["close"][-21])) / max(float(np.sum(np.abs(np.diff(r_m15["close"][-21:])))), 1e-9)
    aligned_dii = max(0.0, dir_sign * dii) if dir_sign != 0 else 0.0
    cronus_ml = 1.0 / (1.0 + math.exp(-((efficiency * 4.5) + (aligned_dii * 3.8) + (0.45 if dir_sign != 0 else -0.6) - 0.75)))

    tf_pts = ((abs(htf_sum) / 3.0) * 32.0) + (10.0 if (dir_sign != 0 and m15_dir == dir_sign) else 0.0)
    delta_pts = min(22.0, (aligned_dii * 85.0) + (tvpin * 10.0 if dir_sign != 0 else 0.0))
    ict_pts = 20.0 if ict_tag == "OB+IFVG" else (16.0 if ict_tag == "VAL-RECLAIM" else (13.0 if ict_tag == "EMA-FLOW" else 4.0))
    ml_pts = cronus_ml * 18.0

    kf_pts = 0.0
    if not kf["is_climax"] and not kf["mm_taxed"]:
        if (dir_sign == 1 and kf["regime_bias"] == "BULL_IMPULSE") or (dir_sign == -1 and kf["regime_bias"] == "BEAR_IMPULSE"):
            kf_pts = 4.0
        if kf["gm_state"] == "FRONT_RUN_FLOW":
            kf_pts += 3.0
    score = min(98.0, max(15.0, tf_pts + delta_pts + ict_pts + ml_pts + kf_pts))
    if kf["is_climax"]:
        score *= 0.78
    if kf["mm_taxed"]:
        score *= 0.76
    if spr_atr > 0.18:
        score *= 0.72


    # Institutional Momentum Delta Adjustments (TSMOM + Skip-Recent-Bars + Hard Crash Veto)
    if mom["mom_crash_veto"]:
        score = min(score * 0.65, float(SILO_CONFIG[sleeve]["gate"]) - 6.0)
    elif mom["is_chasing_spike"] and direction == mom["mom_dir"]:
        score *= 0.80
    elif mom["is_pullback_entry"] and direction == mom["mom_dir"]:
        score = min(99.0, score + 5.0)
    elif mom["mom_dir"] in ("BUY", "SELL") and direction != mom["mom_dir"] and abs(mom["tsmom_z"]) >= 0.65:
        score *= 0.84


    # Ornstein-Uhlenbeck (OU) Mean Reversion & ADF Stationarity Adjustments
    if ou["is_valid_ou"] and direction == ou["ou_dir"]:
        if ou["ou_state"] == "PRIME_OU_SNAPBACK":
            score = min(99.0, score + 4.5)
        elif ou["ou_state"] == "OU_STRETCHED":
            score = min(99.0, score + 2.5)
    elif ou["is_valid_ou"] and direction in ("BUY", "SELL") and ou["ou_dir"] in ("BUY", "SELL") and direction != ou["ou_dir"]:
        # Damp chasing further into an extreme stretch when fast OU mean-reversion pull is active
        score *= 0.85
    elif not ou["is_valid_ou"] and ict_tag == "VAL-RECLAIM":
        # Damp standalone mean-reversion fades when ADF t-stat fails stationarity (random-walk / breakout drift)
        score *= 0.88

    # Dual-Regime Ambiguity Gate: damp entries when BOTH TSMOM is NOISE_DRIFT and OU is RANDOM_WALK_DRIFT
    if mom["mom_state"] == "NOISE_DRIFT" and not ou["is_valid_ou"] and direction in ("BUY", "SELL"):
        score *= 0.84

    return {
        "valid": True,
        "sleeve": sleeve,
        "raw_symbol": sym,
        "symbol": clean_name,
        "tf": tf_label,
        "bid": spot,
        "ask": float(tick.ask),
        "digits": info.digits,
        "atr14": atr14,
        "spr_atr": spr_atr,
        "direction": direction,
        "trend_code": trend_code,
        "ssl_sup": ssl_sup,
        "bsl_res": bsl_res,
        "zone_tag": zone_tag,
        "delta_pts": net_delta_pts,
        "dii": dii,
        "tvpin": tvpin,
        "ict_tag": ict_tag,
        "cronus_ml": round(cronus_ml * 100.0, 0),
        "score": round(score, 0),
        "kf_fv": kf["fair_value"],
        "kf_gain": kf["gain"],
        "kf_z": kf["z_score"],
        "kf_bias": kf["regime_bias"],
        "tox_eff": kf.get("tox_eff", 0.0),
        "gm_state": kf.get("gm_state", "N/A"),
        "as_skew_atr": kf.get("as_skew_atr", 0.0),
        "as_state": kf.get("as_state", "N/A"),
        "gamma_vr": kf.get("gamma_vr", 1.0),
        "gamma_regime": kf.get("gamma_regime", "N/A"),
        "tsmom_z": mom["tsmom_z"],
        "path_r2": mom["path_r2"],
        "last2_atr": mom["last2_atr"],
        "mom_state": mom["mom_state"],
        "ou_half_life": ou["ou_half_life"],
        "adf_tstat": ou["adf_tstat"],
        "ou_z": ou["ou_z"],
        "ou_dir": ou["ou_dir"],
        "ou_state": ou["ou_state"],
    }


def run_live_mc_dd(win_prob: float) -> float:
    rng = np.random.default_rng(42)
    p = min(0.85, max(0.45, win_prob / 100.0 * 0.78))
    outcomes = np.where(rng.random((2000, 40)) < p, 0.0068 * 1.85, -0.0068)
    equity = np.cumprod(1.0 + outcomes, axis=1)
    peaks = np.maximum.accumulate(equity, axis=1)
    return round(float(np.percentile(np.max((peaks - equity) / peaks, axis=1) * 100.0, 95)), 2)


def _record_execution_slippage(
    sleeve: str,
    sym: str,
    ticket: int,
    direction: str,
    lots: float,
    req_px: float,
    fill_px: float,
    info,
    ev: dict,
    utc_dt: datetime,
) -> float:
    """Appends structured execution slippage & microstructure telemetry to execution_slippage_ledger.jsonl."""
    try:
        pt = float(info.point) if (info and info.point > 0) else 1e-5
        tick_sz = float(info.trade_tick_size) if (info and info.trade_tick_size > 0) else pt
        tick_val = float(info.trade_tick_value) if (info and info.trade_tick_value > 0) else 1.0
        actual_px = float(fill_px) if (fill_px and float(fill_px) > 0.0) else float(req_px)
        raw_diff = (actual_px - float(req_px)) if direction == "BUY" else (float(req_px) - actual_px)
        slip_pts = round(raw_diff / pt, 2)
        slip_usd = round((raw_diff / tick_sz) * float(lots) * tick_val, 4)

        record = {
            "ts_utc": utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "utc_hour": utc_dt.hour,
            "sleeve": sleeve,
            "symbol": sym,
            "ticket": int(ticket),
            "direction": direction,
            "lots": round(float(lots), 2),
            "req_price": round(float(req_px), int(info.digits) if info else 5),
            "fill_price": round(actual_px, int(info.digits) if info else 5),
            "slip_pts": slip_pts,
            "slip_usd": slip_usd,
            "spr_atr": round(float(ev.get("spr_atr", 0.0)), 4),
            "score": int(ev.get("score", 0)),
            "ict_tag": ev.get("ict_tag", "NEUTRAL"),
            "kf_z": float(ev.get("kf_z", 0.0)),
            "tox_eff": float(ev.get("tox_eff", 0.0)),
            "gm_state": ev.get("gm_state", "N/A"),
            "as_skew_atr": float(ev.get("as_skew_atr", 0.0)),
            "as_state": ev.get("as_state", "N/A"),
        }
        with SLIPPAGE_LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return slip_pts
    except Exception as exc:
        log.warning(f"[{sleeve}] Slippage ledger write failed for #{ticket}: {exc}")
        return 0.0


def _append_entry_slippage_ledger(sleeve: str, ev: dict, pre_tick, send_res) -> None:
    """Persists pre-order Bid/Ask quote vs. realized MT5 fill price into execution_slippage_ledger.jsonl."""
    try:
        if send_res is None:
            return
        retcode = int(getattr(send_res, "retcode", -1))
        if retcode not in (getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008)):
            return

        sym = str((ev or {}).get("raw_symbol") or (ev or {}).get("symbol") or "")
        side = str((ev or {}).get("direction") or "").upper()
        req_bid = float(getattr(pre_tick, "bid", 0.0) or 0.0)
        req_ask = float(getattr(pre_tick, "ask", 0.0) or 0.0)
        req_price = req_ask if side == "BUY" else (req_bid if side == "SELL" else 0.0)
        fill_price = float(getattr(send_res, "price", 0.0) or 0.0)
        vol = float(getattr(send_res, "volume", 0.0) or 0.0)

        info = mt5.symbol_info(sym) if sym else None
        point = float(getattr(info, "point", 0.0) or 0.0)
        tick_sz = float(getattr(info, "trade_tick_size", 0.0) or point)
        tick_val = float(getattr(info, "trade_tick_value", 0.0) or 0.0)

        slip_pts = 0.0
        slip_usd = 0.0
        if req_price > 0.0 and fill_price > 0.0 and point > 0.0:
            raw_diff = (req_price - fill_price) if side == "BUY" else (fill_price - req_price)
            slip_pts = round(raw_diff / point, 2)
            if tick_sz > 0.0 and tick_val > 0.0 and vol > 0.0:
                slip_usd = round(slip_pts * tick_val * (point / tick_sz) * vol, 4)

        record = {
            "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sleeve": str(sleeve),
            "symbol": sym,
            "side": side,
            "volume": vol,
            "order": int(getattr(send_res, "order", 0) or 0),
            "deal": int(getattr(send_res, "deal", 0) or 0),
            "ticket": int(getattr(send_res, "order", 0) or 0),
            "req_bid": req_bid,
            "req_ask": req_ask,
            "req_price": req_price,
            "fill_price": fill_price,
            "slip_pts": slip_pts,
            "slip_usd": slip_usd,
            "score": (ev or {}).get("score"),
            "tsmom_z": (ev or {}).get("tsmom_z"),
            "ou_state": (ev or {}).get("ou_state"),
        }
        ledger_file = Path(__file__).resolve().parent / "execution_slippage_ledger.jsonl"
        with ledger_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def execute_auto_trigger(sleeve: str, ev: dict, equity: float, fleet_cb_tripped: bool, max_pos: int) -> tuple[str, bool]:
    scfg = SILO_CONFIG[sleeve]
    if fleet_cb_tripped:
        return "CB-3%-HALT", False
    now_utc = datetime.now(timezone.utc)
    mins = now_utc.hour * 60 + now_utc.minute
    if (20 * 60 + 55) <= mins <= (22 * 60 + 10):
        return "ROLLOVER-HOLD", False
    if now_utc.hour not in scfg["utc_hours"]:
        return f"KZ-WAIT({now_utc.hour:02d}UTC)", False
    if ev["spr_atr"] > scfg["max_spr_atr"]:
        return f"SPR-SHIELD({ev['spr_atr']:.2f})", False
    if ev["direction"] not in ("BUY", "SELL"):
        return "FLAT-HOLD", False
    if float(ev["score"]) > scfg["max_score"]:
        return f"CLIMAX-TRAP({int(ev['score'])}%>{int(scfg['max_score'])}%)", False
    if ev.get("ict_tag", "NEUTRAL") not in scfg["allowed_ict"]:
        return f"ICT-FILTER({ev.get('ict_tag', 'NEUTRAL')})", False

    sym = ev["raw_symbol"]
    existing_sym = mt5.positions_get(symbol=sym) or []
    if existing_sym:
        return f"LIVE#{existing_sym[0].ticket}", False

    all_sleeve_pos = mt5.positions_get() or []
    if len(all_sleeve_pos) >= max_pos:
        return f"CAP-MAX({len(all_sleeve_pos)}/{max_pos})", False

    from datetime import timedelta
    day_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(day_start_utc - timedelta(minutes=35), now_utc + timedelta(minutes=5)) or []
    daily_sym_losses = 0
    daily_sleeve_losses = 0
    for d in reversed(deals):
        if d.entry == mt5.DEAL_ENTRY_OUT and float(d.profit) < 0.0:
            if float(d.time) >= day_start_utc.timestamp():
                daily_sleeve_losses += 1
                if d.symbol == sym:
                    daily_sym_losses += 1
            if d.symbol == sym:
                mins_ago = (now_utc.timestamp() - float(d.time)) / 60.0
                if 0.0 <= mins_ago < 30.0:
                    rem = max(1, int(math.ceil(30.0 - mins_ago)))
                    return f"SL-CD({rem}m)", False
    if daily_sym_losses >= 2:
        return f"DAY-SL-LOCK({daily_sym_losses}/2)", False
    if daily_sleeve_losses >= scfg["max_daily_sleeve_losses"]:
        return f"SLV-SL-LOCK({daily_sleeve_losses}/{scfg['max_daily_sleeve_losses']})", False

    if sleeve == "T2" and all_sleeve_pos:
        def _ccy_pair(s_name: str) -> set[str]:
            clean = "".join(ch for ch in s_name.upper() if ch.isalpha())[:6]
            return {clean[:3], clean[3:6]} if len(clean) == 6 else {clean}
        cand_ccys = _ccy_pair(sym)
        for op in all_sleeve_pos:
            shared = cand_ccys.intersection(_ccy_pair(op.symbol))
            if shared:
                return f"CCY-MUTEX({'/'.join(sorted(shared))}:{op.symbol})", False

    info = mt5.symbol_info(sym)
    if info is None or ev["atr14"] <= 0:
        return "SYM-ERR", False

    fill_mode = mt5.ORDER_FILLING_IOC if (info.filling_mode & 2) else (
        mt5.ORDER_FILLING_FOK if (info.filling_mode & 1) else mt5.ORDER_FILLING_RETURN
    )

    risk_usd = min(equity * scfg["risk_pct"], scfg["max_risk_usd"])
    sl_dist = ev["atr14"] * scfg["sl_atr_mult"]
    tick_val = info.trade_tick_value if info.trade_tick_value > 0 else 1.0
    tick_size = info.trade_tick_size if info.trade_tick_size > 0 else info.point

    if sleeve == "T3":
        min_lot_sl_usd = (sl_dist / max(1e-9, tick_size)) * info.volume_min * tick_val
        if min_lot_sl_usd > scfg["max_risk_usd"]:
            return f"ATR-CAP(${min_lot_sl_usd:.1f}>${int(scfg['max_risk_usd'])})", False

    tp_dist = sl_dist * scfg["tp_r_mult"]
    raw_lots = risk_usd / (max(1.0, sl_dist / tick_size) * tick_val)
    step = info.volume_step if info.volume_step > 0 else 0.01
    lots = round(max(info.volume_min, min(info.volume_max, math.floor(raw_lots / step) * step)), 2)

    is_buy = ev["direction"] == "BUY"
    price = ev["ask"] if is_buy else ev["bid"]
    sl = round(price - sl_dist if is_buy else price + sl_dist, info.digits)
    tp = round(price + tp_dist if is_buy else price - tp_dist, info.digits)

    _sym_for_tick = (ev.get("raw_symbol") or ev.get("symbol", "")) if isinstance(ev, dict) else ""
    _pre_tick = mt5.symbol_info_tick(_sym_for_tick) if _sym_for_tick else None
    res = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": lots,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 30,
        "magic": MAGIC_NUMBERS[sleeve],
        "comment": f"ShivSoul60s_{sleeve}_{int(ev['score'])}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": fill_mode,
    })
    _append_entry_slippage_ledger(
        sleeve=sleeve,
        ev=ev,
        pre_tick=_pre_tick,
        send_res=res,
    )
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"[{sleeve}] AUTO-EXEC FILLED: {ev['direction']} {sym} {lots}L @ {price} | SL={sl} TP={tp} | Ticket=#{res.order}")
        return f"EXEC#{res.order}", True

    err_code = res.retcode if res else mt5.last_error()
    log.warning(f"[{sleeve}] ORDER REJECTED on {sym} ({lots}L, fill={fill_mode}): {err_code}")
    return f"GATE({err_code})", False


def upsert_dissolving_hud_card(sleeve: str, text: str, prev_msg_id: int | None, brush_away: bool) -> int | None:
    token = tc.get_bot_token_for_sleeve(sleeve)
    base_url = f"https://api.telegram.org/bot{token}"
    chat_id = tc.TELEGRAM_CHAT_ID

    try:
        if brush_away and prev_msg_id:
            httpx.post(f"{base_url}/deleteMessage", json={"chat_id": chat_id, "message_id": prev_msg_id}, timeout=8.0)
            prev_msg_id = None

        if prev_msg_id:
            r_edit = httpx.post(
                f"{base_url}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": prev_msg_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10.0,
            )
            data = r_edit.json()
            if r_edit.status_code == 200 and data.get("ok"):
                return prev_msg_id
            if "message is not modified" in str(data.get("description", "")).lower():
                return prev_msg_id

        r_send = httpx.post(
            f"{base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10.0,
        )
        sdata = r_send.json()
        if r_send.status_code == 200 and sdata.get("ok"):
            return int(sdata["result"]["message_id"])
    except Exception as exc:
        log.error(f"[{sleeve}] Dissolve HUD update failed: {exc}")
    return prev_msg_id


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"hud_msg_id": {"T1": None, "T2": None, "T3": None}, "cycle_count": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run_dissolve_hud_cycle(force_brush_away: bool = False) -> None:
    state = load_state()
    hud_ids = state.setdefault("hud_msg_id", {"T1": None, "T2": None, "T3": None})
    cycle_num = int(state.get("cycle_count", 0)) + 1
    state["cycle_count"] = cycle_num

    now_utc = datetime.now(timezone.utc)
    ts_hms = now_utc.strftime("%H:%M:%S UTC")
    globe_sweep_tag = get_session_globe_tag(now_utc, cycle_num)

    sleeve_snapshots = {}
    total_fleet_eq = 0.0
    for sleeve in ["T1", "T2", "T3"]:
        cfg = SLEEVES.get(sleeve, {})
        if not cfg:
            continue
        if mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"]):
            acc = mt5.account_info()
            if acc:
                total_fleet_eq += float(acc.equity)
                sleeve_snapshots[sleeve] = round(float(acc.equity), 2)
            mt5.shutdown()

    cb_status = evaluate_weekly_circuit_breaker(total_fleet_eq if total_fleet_eq > 0 else 3000.0, threshold_pct=0.03)
    state["sleeves"] = sleeve_snapshots
    state["fleet_dd_pct"] = cb_status["weekly_dd_pct"]
    state["weekly_anchor_nav"] = cb_status["anchor_nav"]

    for sleeve in ["T1", "T2", "T3"]:
        cfg = SLEEVES.get(sleeve, {})
        scfg = SILO_CONFIG[sleeve]
        if not cfg:
            continue

        if not mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"]):
            log.warning(f"[{sleeve}] MT5 init failed: {mt5.last_error()}")
            continue

        acc = mt5.account_info()
        positions = mt5.positions_get() or []
        orders = mt5.orders_get() or []
        nav = float(acc.balance)
        eq = float(acc.equity)
        pnl = eq - nav
        dd_pct = cb_status["weekly_dd_pct"]
        freem = float(acc.margin_free)

        # 1. Manage open positions (+1.0R Breakeven Lock & +1.5R ATR Trailing Stop)
        be_badges = manage_open_positions(sleeve, positions)
        positions = mt5.positions_get() or []

        exposure_lines = []
        for p in positions:
            info = mt5.symbol_info(p.symbol)
            d = info.digits if info else 5
            side = "BUY" if p.type == 0 else "SELL"
            b_tag = f" [{be_badges[p.ticket]}]" if p.ticket in be_badges else ""
            exposure_lines.append(f"- [{sleeve}] {p.symbol.replace('m', '')} {side} {p.volume:.2f}L @ {p.price_open:.{d}f} ({p.profit:+.2f}){b_tag}")
        for o in orders:
            info = mt5.symbol_info(o.symbol)
            d = info.digits if info else 5
            exposure_lines.append(f"- [{sleeve}] {o.symbol.replace('m', '')} PEND {o.volume_initial:.2f}L @ {o.price_open:.{d}f}")

        # 2. Evaluate all assets first, then rank by highest score so Max-Pos cap picks top setups
        evaluated = []
        for idx, (candidates, tf_lbl) in enumerate(scfg["assets"], start=1):
            sym = resolve_symbol(candidates)
            if not sym:
                continue
            ev = analyze_asset(sym, sleeve, tf_lbl)
            evaluated.append((idx, ev))

        # Execution order: highest composite score first
        exec_order = sorted(
            [item for item in evaluated if item[1].get("valid")],
            key=lambda x: x[1]["score"],
            reverse=True,
        )

        triggered_any = False
        new_order_filled = False
        gate = scfg["gate"]
        max_pos = scfg["max_positions"]

        for _, ev in exec_order:
            if ev["score"] >= gate and ev["direction"] in ("BUY", "SELL") and ev.get("ict_tag", "NEUTRAL") == "NEUTRAL":
                ev["exec_tag"] = "ICT-WAIT"
            elif ev["score"] >= gate and ev["direction"] in ("BUY", "SELL"):
                if sleeve == "T3":
                    mc_dd = run_live_mc_dd(ev["score"])
                    if mc_dd <= 10.0:
                        triggered_any = True
                        tag, filled = execute_auto_trigger(sleeve, ev, eq, cb_status["tripped"], max_pos)
                        ev["exec_tag"] = tag
                        new_order_filled = new_order_filled or filled
                    else:
                        ev["exec_tag"] = f"MC-HOLD({mc_dd}%)"
                else:
                    triggered_any = True
                    tag, filled = execute_auto_trigger(sleeve, ev, eq, cb_status["tripped"], max_pos)
                    ev["exec_tag"] = tag
                    new_order_filled = new_order_filled or filled
            elif ev["spr_atr"] > 0.18:
                ev["exec_tag"] = f"SPR-SHIELD({ev['spr_atr']:.2f})"
            else:
                ev["exec_tag"] = "HUNT"

            log.info(f"[{sleeve}] SCAN {ev['symbol']} {ev['direction']} Score={int(ev['score'])}%/{int(gate)}% ICT={ev['ict_tag']} SprATR={ev['spr_atr']:.3f} -> {ev['exec_tag']}")

        lines = [
            f"*{scfg['title']}*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🟢 {sleeve} `#{acc.login}` | NAV `${nav:,.2f}` | Eq `${eq:,.2f}` (`{pnl:+.2f}`)",
            f"FreeM `${freem:,.2f}` | WkDD `{dd_pct:.2f}%` | Open `{len(positions)}/{max_pos}` | Pend `{len(orders)}`",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⚡ *ACTIVE & PENDING EXPOSURE ({sleeve})*",
        ]
        if exposure_lines:
            lines.extend(exposure_lines)
        else:
            lines.append(f"- [{sleeve}] Flat | Zero Active Exposure")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if cb_status["tripped"]:
            lines.append(f"🛑 *CIRCUIT BREAKER [{sleeve}]: WEEKLY DD {dd_pct:.2f}% >= 3.0% HALT*")
        elif triggered_any:
            lines.append(f"🎯 *ALPHA TRIGGER [{sleeve}]: EDGE >= {gate:.0f}% — AUTO-EXEC ENGAGED*")
        else:
            lines.append(f"🎯 *ALPHA TRIGGER [{sleeve}]: Balanced | Awaiting >= {gate:.0f}% Edge*")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📡 *{sleeve} TOP-DOWN + DELTA + S/R MATRIX*")

        for idx, ev in evaluated:
            if not ev.get("valid"):
                lines.append(f"#{idx} [{sleeve}] {ev['symbol']:<6} ⚪ FLAT [{ev['tf']:<3}]  0%")
                lines.append(f"   Δ:   0 DII:+0.00 tVPIN:0.00 [{ev.get('reason', 'CLOSED')}] [HUNT]")
                continue

            d = ev["digits"]
            dir_badge = "🟢 BUY " if ev["direction"] == "BUY" else ("🔴 SELL" if ev["direction"] == "SELL" else "⚪ FLAT")
            lines.append(
                f"#{idx} [{sleeve}] {ev['symbol']:<6} {dir_badge} [{ev['tf']:<3}] {int(ev['score']):>2d}% | `{ev['trend_code']}`"
            )
            lines.append(
                f"   Δ:{ev['delta_pts']:>+5d} DII:{ev['dii']:>+.2f} tVPIN:{ev['tvpin']:.2f} ML:{int(ev['cronus_ml'])}% [{ev['ict_tag']}] [{ev['exec_tag']}]"
            )
            lines.append(
                f"   S/R: `{ev['ssl_sup']:.{d}f}` .. `{ev['bid']:.{d}f}` .. `{ev['bsl_res']:.{d}f}` (`{ev['zone_tag']}`)"
            )

        if sleeve == "T3":
            xau_sc = evaluated[0][1].get("score", 60.0) if evaluated else 60.0
            lines.append(f"🎲 *T3 Live 2,000-Path MC:* P95 DD `{run_live_mc_dd(xau_sc)}%` (`<= 10.0%` Gate)")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{globe_sweep_tag} | `{ts_hms}` | `HUD#{cycle_num}`")
        lines.append(f"🎯 Gate: {scfg['gate_label']}")

        card_text = "\n".join(lines)

        should_brush = force_brush_away or new_order_filled or (cycle_num % BRUSH_AWAY_EVERY_CYCLES == 0)
        new_id = upsert_dissolving_hud_card(sleeve, card_text, hud_ids.get(sleeve), brush_away=should_brush)
        if new_id:
            hud_ids[sleeve] = new_id
            log.info(f"[{sleeve}] Cycle #{cycle_num} HUD {'brushed-away & refreshed' if should_brush else 'dissolved in-place'} (msg_id={new_id})")

        mt5.shutdown()

    save_state(state)


if __name__ == "__main__":
    log.info("Starting 🔱 SHIVSOUL NEXUS v6.0 Auto-Scan, Auto-Fire & BE/ATR-Trail HUD Engine...")
    run_dissolve_hud_cycle(force_brush_away=True)
    while True:
        time.sleep(60)
        try:
            run_dissolve_hud_cycle(force_brush_away=False)
        except Exception as err:
            log.exception(f"Unhandled error in Dissolve HUD 60s loop: {err}")



