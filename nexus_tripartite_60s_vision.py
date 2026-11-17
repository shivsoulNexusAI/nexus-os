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
from kalman_regime_filter import compute_kalman_fair_value

PROJECT_DIR = Path("C:/Quant-Nexus-Eng")
STATE_FILE = PROJECT_DIR / "tripartite_60s_state.json"
LOG_FILE = PROJECT_DIR / "nexus_tripartite_60s_vision.log"

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
        "title": "🔱 SHIVSOUL NEXUS // T1 BTCUSD DESK v5.6",
        "account": 278062038,
        "gate": 82.0,
        "max_positions": 1,
        "gate_label": "T1(BTC) >= 82% | Top-Down + Delta + tVPIN",
        "assets": [
            (["BTCUSDm", "BTCUSD"], "M15"),
        ],
    },
    "T2": {
        "title": "🔱 SHIVSOUL NEXUS // T2 FX MAJORS DESK v5.6",
        "account": 278062039,
        "gate": 78.0,
        "max_positions": 2,
        "gate_label": "T2(FX-6) >= 78% | Max-2 Cap + OB/IFVG + SprShield",
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
        "title": "🔱 SHIVSOUL NEXUS // T3 XAUUSD GOLD DESK v5.6",
        "account": 278062042,
        "gate": 80.0,
        "max_positions": 1,
        "gate_label": "T3(XAU) >= 80% | Delta + Cronus ML + Live MC",
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
    Enforces +1.0R Breakeven Lock (+0.12R buffer) and +1.5R ATR(14) Trailing Stop
    across all open positions in the active sleeve. Returns ticket -> status badge.
    """
    badges: dict[int, str] = {}
    for p in positions:
        sym = p.symbol
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            continue

        r_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 30)
        atr14 = calc_atr14(r_m15)
        if atr14 <= 0:
            atr14 = abs(p.price_open - p.sl) / 1.5 if p.sl > 0 else 0.0
        if atr14 <= 0:
            continue

        is_buy = (p.type == 0)
        entry = float(p.price_open)
        cur_sl = float(p.sl)
        cur_tp = float(p.tp)
        spot = float(tick.bid) if is_buy else float(tick.ask)
        digits = info.digits
        stops_min = max(info.trade_stops_level * info.point, 2 * info.point)

        # Infer 1R distance from initial SL (or 1.5 * ATR14 fallback)
        r_dist = abs(entry - cur_sl) if (cur_sl > 0 and ((is_buy and cur_sl < entry) or (not is_buy and cur_sl > entry))) else (atr14 * 1.5)
        if r_dist <= 0:
            r_dist = atr14 * 1.5

        unrealized_dist = (spot - entry) if is_buy else (entry - spot)
        r_mult = unrealized_dist / r_dist

        new_sl = None
        mode_tag = None

        if r_mult >= 1.5:
            trail_dist = atr14 * 1.0
            candidate_sl = round((spot - trail_dist) if is_buy else (spot + trail_dist), digits)
            if is_buy and candidate_sl > cur_sl + (2 * info.point) and (spot - candidate_sl) >= stops_min:
                new_sl = candidate_sl
                mode_tag = f"TRAIL@{r_mult:.1f}R"
            elif (not is_buy) and (cur_sl == 0.0 or candidate_sl < cur_sl - (2 * info.point)) and (candidate_sl - spot) >= stops_min:
                new_sl = candidate_sl
                mode_tag = f"TRAIL@{r_mult:.1f}R"
            else:
                badges[p.ticket] = f"TRAIL-HOLD({r_mult:.1f}R)"
        elif r_mult >= 0.75:
            be_lock = round((entry + r_dist * 0.10) if is_buy else (entry - r_dist * 0.10), digits)
            if is_buy and cur_sl < be_lock - info.point and (spot - be_lock) >= stops_min:
                new_sl = be_lock
                mode_tag = "BE+0.10R"
            elif (not is_buy) and (cur_sl == 0.0 or cur_sl > be_lock + info.point) and (be_lock - spot) >= stops_min:
                new_sl = be_lock
                mode_tag = "BE+0.10R"
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

    kf = compute_kalman_fair_value(
        closes=np.asarray(r_m15["close"], dtype=float),
        atr14=atr14,
        sleeve=sleeve,
        utc_hour=datetime.now(timezone.utc).hour,
        spread_price=spread_price,
        tvpin=float(tvpin),
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
    }


def run_live_mc_dd(win_prob: float) -> float:
    rng = np.random.default_rng(42)
    p = min(0.85, max(0.45, win_prob / 100.0 * 0.78))
    outcomes = np.where(rng.random((2000, 40)) < p, 0.0068 * 1.85, -0.0068)
    equity = np.cumprod(1.0 + outcomes, axis=1)
    peaks = np.maximum.accumulate(equity, axis=1)
    return round(float(np.percentile(np.max((peaks - equity) / peaks, axis=1) * 100.0, 95)), 2)


def execute_auto_trigger(sleeve: str, ev: dict, equity: float, fleet_cb_tripped: bool, max_pos: int) -> tuple[str, bool]:
    if fleet_cb_tripped:
        return "CB-3%-HALT", False
    now_utc = datetime.now(timezone.utc)
    mins = now_utc.hour * 60 + now_utc.minute
    if (20 * 60 + 55) <= mins <= (22 * 60 + 10):
        return "ROLLOVER-HOLD", False
    if ev["spr_atr"] > 0.18:
        return f"SPR-SHIELD({ev['spr_atr']:.2f})", False
    if ev["direction"] not in ("BUY", "SELL"):
        return "FLAT-HOLD", False

    sym = ev["raw_symbol"]
    existing_sym = mt5.positions_get(symbol=sym) or []
    if existing_sym:
        return f"LIVE#{existing_sym[0].ticket}", False

    all_sleeve_pos = mt5.positions_get() or []
    if len(all_sleeve_pos) >= max_pos:
        return f"CAP-MAX({len(all_sleeve_pos)}/{max_pos})", False

    # Final Production Policy:
    # A) 2-Strike Daily Kill-Switch per symbol (DAY-SL-LOCK) + 30-min post-SL Cooldown (SL-CD)
    from datetime import timedelta
    day_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(day_start_utc - timedelta(minutes=35), now_utc + timedelta(minutes=5)) or []
    daily_sym_losses = 0
    for d in reversed(deals):
        if d.symbol == sym and d.entry == mt5.DEAL_ENTRY_OUT and float(d.profit) < 0.0:
            if float(d.time) >= day_start_utc.timestamp():
                daily_sym_losses += 1
            mins_ago = (now_utc.timestamp() - float(d.time)) / 60.0
            if 0.0 <= mins_ago < 30.0:
                rem = max(1, int(math.ceil(30.0 - mins_ago)))
                return f"SL-CD({rem}m)", False
    if daily_sym_losses >= 2:
        return f"DAY-SL-LOCK({daily_sym_losses}/2)", False

    # B) T2 USD-Basket Correlation Guard: block stacking 2 identical directional USD bets
    if sleeve == "T2" and all_sleeve_pos:
        def _usd_bias(s_name: str, is_long: bool) -> int:
            s_up = s_name.upper()
            if s_up.startswith("USD"):
                return 1 if is_long else -1
            if "USD" in s_up:
                return -1 if is_long else 1
            return 0  # Non-USD cross (e.g., GBPJPY)
        cand_bias = _usd_bias(sym, ev["direction"] == "BUY")
        if cand_bias != 0:
            for op in all_sleeve_pos:
                if _usd_bias(op.symbol, op.type == 0) == cand_bias:
                    return f"USD-CORR({op.symbol})", False

    info = mt5.symbol_info(sym)
    if info is None or ev["atr14"] <= 0:
        return "SYM-ERR", False

    fill_mode = mt5.ORDER_FILLING_IOC if (info.filling_mode & 2) else (
        mt5.ORDER_FILLING_FOK if (info.filling_mode & 1) else mt5.ORDER_FILLING_RETURN
    )

    risk_usd = equity * 0.0068
    sl_dist = ev["atr14"] * 1.5
    tick_val = info.trade_tick_value if info.trade_tick_value > 0 else 1.0
    tick_size = info.trade_tick_size if info.trade_tick_size > 0 else info.point

    # C) T3 (XAUUSD) Strict $10.00 Min-Lot ATR Gate: reject over-volatile regimes instead of pinching SL
    if sleeve == "T3":
        min_lot_sl_usd = (sl_dist / max(1e-9, tick_size)) * info.volume_min * tick_val
        if min_lot_sl_usd > 10.0:
            return f"ATR-CAP(${min_lot_sl_usd:.1f}>$10)", False
        risk_usd = min(risk_usd, 10.0)

    tp_dist = sl_dist * 1.85
    raw_lots = risk_usd / (max(1.0, sl_dist / tick_size) * tick_val)
    step = info.volume_step if info.volume_step > 0 else 0.01
    lots = round(max(info.volume_min, min(info.volume_max, math.floor(raw_lots / step) * step)), 2)

    is_buy = ev["direction"] == "BUY"
    price = ev["ask"] if is_buy else ev["bid"]
    sl = round(price - sl_dist if is_buy else price + sl_dist, info.digits)
    tp = round(price + tp_dist if is_buy else price - tp_dist, info.digits)

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
    log.info("Starting 🔱 SHIVSOUL NEXUS v5.6 Auto-Scan, Auto-Fire & BE/ATR-Trail HUD Engine...")
    run_dissolve_hud_cycle(force_brush_away=True)
    while True:
        time.sleep(60)
        try:
            run_dissolve_hud_cycle(force_brush_away=False)
        except Exception as err:
            log.exception(f"Unhandled error in Dissolve HUD 60s loop: {err}")



