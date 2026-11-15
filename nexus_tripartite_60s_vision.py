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
from nexus_ship_core import SLEEVES, is_valid_live_tick

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
        "gate_label": "T1(BTC) >= 82% | Top-Down + Delta + tVPIN",
        "assets": [
            (["BTCUSDm", "BTCUSD"], "M15"),
        ],
    },
    "T2": {
        "title": "🔱 SHIVSOUL NEXUS // T2 FX MAJORS DESK v5.6",
        "account": 278062039,
        "gate": 78.0,
        "gate_label": "T2(FX-6) >= 78% | Top-Down + OB/IFVG + SprShield",
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
        "gate_label": "T3(XAU) >= 80% | Delta + Cronus ML + Live MC",
        "assets": [
            (["XAUUSDm", "XAUUSD"], "M15"),
        ],
    },
}

# Brush away (delete old HUD & post fresh card) every 60 cycles (1 hour) or on live trade execution
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

    # 1. Top-Down Multi-Timeframe Structure (D1, H4, H1, M15)
    d1_dir = 1 if r_d1["close"][-1] > ema(r_d1["close"], 20) else -1
    h4_dir = 1 if r_h4["close"][-1] > ema(r_h4["close"], 20) else -1
    h1_dir = 1 if r_h1["close"][-1] > ema(r_h1["close"], 20) else -1
    m15_dir = 1 if r_m15["close"][-1] > ema(r_m15["close"], 20) else -1

    htf_sum = d1_dir + h4_dir + h1_dir
    if htf_sum >= 2:
        direction = "BUY"
        dir_sign = 1
    elif htf_sum <= -2:
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

    # 3. Tick-Delta (Δ), Directional Imbalance Index (DII), and tVPIN
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

    # 4. ICT Structure Tag (OB+IFVG / VAL-RECLAIM / NEUTRAL)
    c0, c1 = r_m15["close"][-4], r_m15["close"][-3]
    h0, l0 = r_m15["high"][-4], r_m15["low"][-4]
    h2, l2 = r_m15["high"][-2], r_m15["low"][-2]
    bull_fvg = l2 > h0 and c1 > c0
    bear_fvg = h2 < l0 and c1 < c0
    fvg_match = (dir_sign == 1 and bull_fvg) or (dir_sign == -1 and bear_fvg)

    if fvg_match:
        ict_tag = "OB+IFVG"
    elif (dir_sign == 1 and rng_pct <= 35.0) or (dir_sign == -1 and rng_pct >= 65.0):
        ict_tag = "VAL-RECLAIM"
    else:
        ict_tag = "NEUTRAL"

    # 5. Cronus ML & Composite Score
    efficiency = abs(float(r_m15["close"][-1] - r_m15["close"][-21])) / max(float(np.sum(np.abs(np.diff(r_m15["close"][-21:])))), 1e-9)
    cronus_ml = 1.0 / (1.0 + math.exp(-((efficiency * 4.2) + (abs(dii) * 2.1) - 1.35)))

    htf_pts = (abs(htf_sum) / 3.0) * 34.0
    delta_pts = min(24.0, (max(0.0, dir_sign * dii) if dir_sign != 0 else abs(dii) * 0.4) * 44.0)
    ict_pts = 22.0 if ict_tag == "OB+IFVG" else (14.0 if ict_tag == "VAL-RECLAIM" else 5.0)
    ml_pts = cronus_ml * 20.0

    score = min(99.0, max(15.0, htf_pts + delta_pts + ict_pts + ml_pts))
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
    }


def run_live_mc_dd(win_prob: float) -> float:
    rng = np.random.default_rng(42)
    p = min(0.85, max(0.45, win_prob / 100.0 * 0.78))
    outcomes = np.where(rng.random((2000, 40)) < p, 0.0068 * 1.85, -0.0068)
    equity = np.cumprod(1.0 + outcomes, axis=1)
    peaks = np.maximum.accumulate(equity, axis=1)
    return round(float(np.percentile(np.max((peaks - equity) / peaks, axis=1) * 100.0, 95)), 2)


def execute_auto_trigger(sleeve: str, ev: dict, equity: float) -> tuple[str, bool]:
    now_utc = datetime.now(timezone.utc)
    mins = now_utc.hour * 60 + now_utc.minute
    if (20 * 60 + 55) <= mins <= (22 * 60 + 10):
        return "ROLLOVER-HOLD", False
    if ev["spr_atr"] > 0.18:
        return f"SPR-SHIELD({ev['spr_atr']:.2f})", False
    if ev["direction"] not in ("BUY", "SELL"):
        return "FLAT-HOLD", False

    sym = ev["raw_symbol"]
    existing = mt5.positions_get(symbol=sym) or []
    if existing:
        return f"LIVE#{existing[0].ticket}", False

    info = mt5.symbol_info(sym)
    if info is None or ev["atr14"] <= 0:
        return "SYM-ERR", False

    risk_usd = equity * 0.0068
    sl_dist = ev["atr14"] * 1.5
    tp_dist = sl_dist * 1.85
    tick_val = info.trade_tick_value if info.trade_tick_value > 0 else 1.0
    tick_size = info.trade_tick_size if info.trade_tick_size > 0 else info.point
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
        "deviation": 25,
        "magic": MAGIC_NUMBERS[sleeve],
        "comment": f"ShivSoul60s_{sleeve}_{int(ev['score'])}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    })
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        return f"EXEC#{res.order}", True
    return f"GATE({res.retcode if res else 'ERR'})", False


def upsert_dissolving_hud_card(sleeve: str, text: str, prev_msg_id: int | None, brush_away: bool) -> int | None:
    """Dissolves previous 60s dashboard in-place via editMessageText, or brushes away & posts fresh."""
    token = tc.get_bot_token_for_sleeve(sleeve)
    base_url = f"https://api.telegram.org/bot{token}"
    chat_id = tc.TELEGRAM_CHAT_ID

    try:
        # 1. If brush_away is requested (e.g. every 60 cycles or on new trade fill), delete old HUD & send fresh
        if brush_away and prev_msg_id:
            httpx.post(f"{base_url}/deleteMessage", json={"chat_id": chat_id, "message_id": prev_msg_id}, timeout=8.0)
            prev_msg_id = None

        # 2. Try in-place dissolve (editMessageText) on existing HUD card
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
            # If Telegram says "message is not modified", keep the exact message_id
            if "message is not modified" in str(data.get("description", "")).lower():
                return prev_msg_id

        # 3. Otherwise send a brand-new HUD message and capture its message_id
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
        dd_pct = max(0.0, ((nav - eq) / nav) * 100.0) if nav > 0 else 0.0
        freem = float(acc.margin_free)

        exposure_lines = []
        for p in positions:
            info = mt5.symbol_info(p.symbol)
            d = info.digits if info else 5
            side = "BUY" if p.type == 0 else "SELL"
            exposure_lines.append(f"- [{sleeve}] {p.symbol.replace('m', '')} {side} {p.volume:.2f}L @ {p.price_open:.{d}f} ({p.profit:+.2f})")
        for o in orders:
            info = mt5.symbol_info(o.symbol)
            d = info.digits if info else 5
            exposure_lines.append(f"- [{sleeve}] {o.symbol.replace('m', '')} PEND {o.volume_initial:.2f}L @ {o.price_open:.{d}f}")

        silo_results = []
        triggered_any = False
        new_order_filled = False
        gate = scfg["gate"]

        for idx, (candidates, tf_lbl) in enumerate(scfg["assets"], start=1):
            sym = resolve_symbol(candidates)
            if not sym:
                continue
            ev = analyze_asset(sym, sleeve, tf_lbl)
            if ev.get("valid") and ev["score"] >= gate and ev["direction"] in ("BUY", "SELL"):
                if sleeve == "T3":
                    mc_dd = run_live_mc_dd(ev["score"])
                    if mc_dd <= 10.0:
                        triggered_any = True
                        tag, filled = execute_auto_trigger(sleeve, ev, eq)
                        ev["exec_tag"] = tag
                        new_order_filled = new_order_filled or filled
                    else:
                        ev["exec_tag"] = f"MC-HOLD({mc_dd}%)"
                else:
                    triggered_any = True
                    tag, filled = execute_auto_trigger(sleeve, ev, eq)
                    ev["exec_tag"] = tag
                    new_order_filled = new_order_filled or filled
            elif ev.get("valid") and ev["spr_atr"] > 0.18:
                ev["exec_tag"] = f"SPR-SHIELD({ev['spr_atr']:.2f})"
            else:
                ev["exec_tag"] = "HUNT"
            silo_results.append((idx, ev))

        lines = [
            f"*{scfg['title']}*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🟢 {sleeve} `#{acc.login}` | NAV `${nav:,.2f}` | Eq `${eq:,.2f}` (`{pnl:+.2f}`)",
            f"FreeM `${freem:,.2f}` | DD `{dd_pct:.2f}%` | Open `{len(positions)}` | Pend `{len(orders)}`",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⚡ *ACTIVE & PENDING EXPOSURE ({sleeve})*",
        ]
        if exposure_lines:
            lines.extend(exposure_lines)
        else:
            lines.append(f"- [{sleeve}] Flat | Zero Active Exposure")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if triggered_any:
            lines.append(f"🎯 *ALPHA TRIGGER [{sleeve}]: EDGE >= {gate:.0f}% — AUTO-EXEC ENGAGED*")
        else:
            lines.append(f"🎯 *ALPHA TRIGGER [{sleeve}]: Balanced | Awaiting >= {gate:.0f}% Edge*")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📡 *{sleeve} TOP-DOWN + DELTA + S/R MATRIX*")

        for idx, ev in silo_results:
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
            xau_sc = silo_results[0][1].get("score", 60.0) if silo_results else 60.0
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
    log.info("Starting 🔱 SHIVSOUL NEXUS v5.6 60-Second Auto-Dissolve HUD Engine...")
    run_dissolve_hud_cycle(force_brush_away=True)
    while True:
        time.sleep(60)
        try:
            run_dissolve_hud_cycle(force_brush_away=False)
        except Exception as err:
            log.exception(f"Unhandled error in Dissolve HUD 60s loop: {err}")