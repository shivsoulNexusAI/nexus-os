# =====================================================================
# SHIVSOUL NEXUS v8.0 // ZERO-LOOKAHEAD 2025-2026 MULTI-SLEEVE BACKTEST
# =====================================================================
import csv
import math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import MetaTrader5 as mt5

from nexus_ship_core import SLEEVES
from nexus_tripartite_60s_vision import resolve_symbol
from nexus_sleeve_worker import VISION_PROFILES
from kalman_regime_filter import compute_kalman_fair_value, compute_momentum_alpha, compute_ou_mean_reversion

START_UTC = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
END_UTC = datetime(2026, 11, 17, 23, 59, tzinfo=timezone.utc)
WARMUP_START_UTC = datetime(2024, 11, 15, 0, 0, tzinfo=timezone.utc)
INITIAL_EQUITY_PER_SLEEVE = 1000.0
REPORT_CSV = Path(r"C:\Quant-Nexus-Eng\reports\backtest_v8_2025_2026.csv")

SLIPPAGE_POINTS = {
    "T1": 150.0,  # $1.50 BTC slippage per side
    "T2": 2.0,    # 0.2 pips FX slippage per side
    "T3": 15.0,   # $0.15 Gold slippage per side
}


def ema_series(arr: np.ndarray, span: int) -> np.ndarray:
    out = np.empty_like(arr, dtype=float)
    if len(arr) == 0:
        return out
    alpha = 2.0 / (span + 1.0)
    out[0] = float(arr[0])
    for i in range(1, len(arr)):
        out[i] = alpha * float(arr[i]) + (1.0 - alpha) * out[i - 1]
    return out


def atr14_series(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n, dtype=float)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])),
    )
    atr = np.zeros(n, dtype=float)
    for i in range(14, n):
        atr[i] = float(np.mean(tr[i - 13 : i + 1]))
    return atr


def fetch_historical_bundle(sleeve: str, candidates: list[str]) -> dict | None:
    sym = resolve_symbol(candidates)
    if not sym:
        return None
    sinfo = mt5.symbol_info(sym)
    if sinfo is None:
        return None

    r_m15 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, WARMUP_START_UTC, END_UTC)
    r_h1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, WARMUP_START_UTC, END_UTC)
    r_h4 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H4, WARMUP_START_UTC, END_UTC)
    r_d1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, WARMUP_START_UTC, END_UTC)

    import time
    mt5.symbol_select(sym, True)
    for _ in range(3):
        if r_m15 is None or len(r_m15) < 500:
            r_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 75000)
        if r_h1 is None or len(r_h1) < 200:
            r_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 20000)
        if r_h4 is None or len(r_h4) < 100:
            r_h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 6000)
        if r_d1 is None or len(r_d1) < 60:
            r_d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 1000)
        if all(r is not None and len(r) >= 60 for r in (r_m15, r_h1, r_h4, r_d1)):
            break
        time.sleep(2.0)

    # Cross-terminal history cache fallback (e.g., if XAUUSD history is already cached on T1/T2 terminal)
    if any(r is None or len(r) < 60 for r in (r_m15, r_h1, r_h4, r_d1)):
        for alt_slv, alt_cfg in SLEEVES.items():
            if alt_slv == sleeve:
                continue
            mt5.shutdown()
            if mt5.initialize(path=alt_cfg["path"], login=alt_cfg["login"], password=alt_cfg["password"], server=alt_cfg["server"], timeout=30000):
                alt_sym = resolve_symbol(candidates)
                if alt_sym:
                    mt5.symbol_select(alt_sym, True)
                    r_m15 = mt5.copy_rates_from_pos(alt_sym, mt5.TIMEFRAME_M15, 0, 75000)
                    r_h1 = mt5.copy_rates_from_pos(alt_sym, mt5.TIMEFRAME_H1, 0, 20000)
                    r_h4 = mt5.copy_rates_from_pos(alt_sym, mt5.TIMEFRAME_H4, 0, 6000)
                    r_d1 = mt5.copy_rates_from_pos(alt_sym, mt5.TIMEFRAME_D1, 0, 1000)
                    if all(r is not None and len(r) >= 60 for r in (r_m15, r_h1, r_h4, r_d1)):
                        print(f"  [INFO] Loaded {alt_sym} history via {alt_slv} terminal cache.")
                        break

    if any(r is None or len(r) < 60 for r in (r_m15, r_h1, r_h4, r_d1)):
        counts = [len(r) if r is not None else 0 for r in (r_m15, r_h1, r_h4, r_d1)]
        print(f"  [WARN] Insufficient MT5 bar history for {sym} (M15/H1/H4/D1 counts={counts}).")
        return None

    return {
        "sleeve": sleeve,
        "symbol": sym,
        "clean_name": sym.replace("m", ""),
        "digits": int(sinfo.digits),
        "point": float(sinfo.point),
        "tick_val": float(sinfo.trade_tick_value) or 1.0,
        "tick_sz": float(sinfo.trade_tick_size) or float(sinfo.point),
        "vol_min": float(sinfo.volume_min) or 0.01,
        "vol_max": float(sinfo.volume_max) or 10.0,
        "vol_step": float(sinfo.volume_step) or 0.01,
        "m15": r_m15,
        "h1": r_h1,
        "h4": r_h4,
        "d1": r_d1,
    }


def simulate_sleeve(sleeve: str, bundles: list[dict]) -> tuple[list[dict], dict]:
    prof = VISION_PROFILES[sleeve]
    equity = INITIAL_EQUITY_PER_SLEEVE
    peak_equity = equity
    max_dd_pct = 0.0
    trades: list[dict] = []

    # Precompute arrays & HTF EMA20 alignment for each symbol in sleeve
    prepared = []
    for b in bundles:
        m15 = b["m15"]
        h1, h4, d1 = b["h1"], b["h4"], b["d1"]
        m_close = m15["close"].astype(float)
        m_open = m15["open"].astype(float)
        m_high = m15["high"].astype(float)
        m_low = m15["low"].astype(float)
        m_vol = m15["tick_volume"].astype(float)
        m_spr = m15["spread"].astype(float)
        m_time = m15["time"].astype(np.int64)

        prepared.append({
            **b,
            "m_time": m_time,
            "m_open": m_open,
            "m_high": m_high,
            "m_low": m_low,
            "m_close": m_close,
            "m_vol": m_vol,
            "m_spr": m_spr,
            "m_ema9": ema_series(m_close, 9),
            "m_ema20": ema_series(m_close, 20),
            "m_ema21": ema_series(m_close, 21),
            "m_atr14": atr14_series(m_high, m_low, m_close),
            "h1_time": h1["time"].astype(np.int64),
            "h1_high": h1["high"].astype(float),
            "h1_low": h1["low"].astype(float),
            "h1_close": h1["close"].astype(float),
            "h1_ema20": ema_series(h1["close"].astype(float), 20),
            "h4_time": h4["time"].astype(np.int64),
            "h4_close": h4["close"].astype(float),
            "h4_ema20": ema_series(h4["close"].astype(float), 20),
            "d1_time": d1["time"].astype(np.int64),
            "d1_close": d1["close"].astype(float),
            "d1_ema20": ema_series(d1["close"].astype(float), 20),
        })

    if not prepared:
        return [], {"sleeve": sleeve, "profile": prof["name"], "trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_pnl": 0.0, "return_pct": 0.0, "max_dd_pct": 0.0, "final_eq": equity, "expectancy": 0.0}

    # Master clock driven by primary asset M15 timestamps from 2025-01-01 onward
    primary = prepared[0]
    start_ts = int(START_UTC.timestamp())
    start_idx = max(80, int(np.searchsorted(primary["m_time"], start_ts)))

    open_pos: dict | None = None
    daily_losses: dict[str, int] = {}
    last_sl_ts_by_sym: dict[str, int] = {}

    for i in range(start_idx, len(primary["m_time"]) - 1):
        bar_ts = int(primary["m_time"][i])
        dt_utc = datetime.fromtimestamp(bar_ts, timezone.utc)
        day_key = dt_utc.strftime("%Y-%m-%d")

        # 1. Manage Open Position on current M15 bar High/Low/Close
        if open_pos is not None:
            pb = open_pos["bundle"]
            idx = int(np.searchsorted(pb["m_time"], bar_ts))
            if idx < len(pb["m_time"]) and int(pb["m_time"][idx]) == bar_ts:
                hi = pb["m_high"][idx]
                lo = pb["m_low"][idx]
                cl = pb["m_close"][idx]
                atr = pb["m_atr14"][idx]
                is_buy = open_pos["direction"] == "BUY"
                entry = open_pos["entry"]
                r_dist = open_pos["r_dist"]
                slip_px = SLIPPAGE_POINTS[sleeve] * pb["point"]

                # Check worst-case intra-bar SL hit first
                sl_hit = (lo <= open_pos["sl"]) if is_buy else (hi >= open_pos["sl"])
                tp_hit = (hi >= open_pos["tp"]) if is_buy else (lo <= open_pos["tp"])

                if sl_hit:
                    exit_px = (open_pos["sl"] - slip_px) if is_buy else (open_pos["sl"] + slip_px)
                    raw_diff = (exit_px - entry) if is_buy else (entry - exit_px)
                    pnl = (raw_diff / pb["tick_sz"]) * pb["tick_val"] * open_pos["rem_lots"]
                    total_trade_pnl = open_pos["realized_partial_pnl"] + pnl
                    equity += pnl
                    if total_trade_pnl < 0:
                        daily_losses[day_key] = daily_losses.get(day_key, 0) + 1
                        last_sl_ts_by_sym[pb["symbol"]] = bar_ts
                    trades.append({
                        "sleeve": sleeve,
                        "symbol": pb["clean_name"],
                        "direction": open_pos["direction"],
                        "open_utc": open_pos["open_utc"],
                        "close_utc": dt_utc.strftime("%Y-%m-%d %H:%M"),
                        "lots": open_pos["init_lots"],
                        "entry": round(entry, pb["digits"]),
                        "exit": round(exit_px, pb["digits"]),
                        "net_pnl": round(total_trade_pnl, 2),
                        "r_realized": round(total_trade_pnl / max(open_pos["risk_usd"], 1e-6), 2),
                        "exit_reason": "TRAIL/BE_SL" if open_pos["be_locked"] else "INIT_SL",
                        "ict_tag": open_pos["ict_tag"],
                        "score": open_pos["score"],
                    })
                    open_pos = None
                elif tp_hit:
                    exit_px = (open_pos["tp"] - slip_px) if is_buy else (open_pos["tp"] + slip_px)
                    raw_diff = (exit_px - entry) if is_buy else (entry - exit_px)
                    pnl = (raw_diff / pb["tick_sz"]) * pb["tick_val"] * open_pos["rem_lots"]
                    total_trade_pnl = open_pos["realized_partial_pnl"] + pnl
                    equity += pnl
                    trades.append({
                        "sleeve": sleeve,
                        "symbol": pb["clean_name"],
                        "direction": open_pos["direction"],
                        "open_utc": open_pos["open_utc"],
                        "close_utc": dt_utc.strftime("%Y-%m-%d %H:%M"),
                        "lots": open_pos["init_lots"],
                        "entry": round(entry, pb["digits"]),
                        "exit": round(exit_px, pb["digits"]),
                        "net_pnl": round(total_trade_pnl, 2),
                        "r_realized": round(total_trade_pnl / max(open_pos["risk_usd"], 1e-6), 2),
                        "exit_reason": "TAKE_PROFIT",
                        "ict_tag": open_pos["ict_tag"],
                        "score": open_pos["score"],
                    })
                    open_pos = None
                else:
                    # Intra-bar favorable excursion updates (Partial Harvest, Profit-BE, ATR Trail)
                    fav_px = hi if is_buy else lo
                    fav_r = ((fav_px - entry) if is_buy else (entry - fav_px)) / max(r_dist, 1e-9)

                    partial_r = prof.get("partial_tp_r", 0.0)
                    if partial_r > 0.0 and fav_r >= partial_r and not open_pos["partial_done"]:
                        half_lots = round(math.floor((open_pos["rem_lots"] * 0.5) / pb["vol_step"]) * pb["vol_step"], 2)
                        if half_lots >= pb["vol_min"] and (open_pos["rem_lots"] - half_lots) >= pb["vol_min"]:
                            p_px = (entry + r_dist * partial_r) if is_buy else (entry - r_dist * partial_r)
                            p_pnl = ((r_dist * partial_r) / pb["tick_sz"]) * pb["tick_val"] * half_lots
                            open_pos["realized_partial_pnl"] += p_pnl
                            open_pos["rem_lots"] = round(open_pos["rem_lots"] - half_lots, 2)
                            open_pos["partial_done"] = True
                            equity += p_pnl

                    if fav_r >= prof["trail_trigger_r"] and atr > 0:
                        t_dist = atr * prof["trail_atr_mult"]
                        cand_sl = round((cl - t_dist) if is_buy else (cl + t_dist), pb["digits"])
                        if is_buy and cand_sl > open_pos["sl"]:
                            open_pos["sl"] = cand_sl
                            open_pos["be_locked"] = True
                        elif (not is_buy) and cand_sl < open_pos["sl"]:
                            open_pos["sl"] = cand_sl
                            open_pos["be_locked"] = True
                    elif fav_r >= prof["be_trigger_r"] and not open_pos["be_locked"]:
                        lock_dist = r_dist * prof["be_lock_r"]
                        be_sl = round((entry + lock_dist) if is_buy else (entry - lock_dist), pb["digits"])
                        if (is_buy and be_sl > open_pos["sl"]) or ((not is_buy) and be_sl < open_pos["sl"]):
                            open_pos["sl"] = be_sl
                            open_pos["be_locked"] = True

            peak_equity = max(peak_equity, equity)
            dd = ((peak_equity - equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            max_dd_pct = max(max_dd_pct, dd)

        # 2. Evaluate New Entries when flat inside Killzone hours
        if open_pos is not None:
            continue
        if dt_utc.hour not in prof["utc_hours"]:
            continue
        if daily_losses.get(day_key, 0) >= prof["max_daily_losses"]:
            continue

        candidates_scored = []
        for pb in prepared:
            idx = int(np.searchsorted(pb["m_time"], bar_ts))
            if idx < 70 or idx >= len(pb["m_time"]) or int(pb["m_time"][idx]) != bar_ts:
                continue
            if (bar_ts - last_sl_ts_by_sym.get(pb["symbol"], 0)) < 2700:  # 45m post-SL cooldown
                continue

            atr14 = pb["m_atr14"][idx]
            if atr14 <= 0.0:
                continue
            if sleeve == "T3" and atr14 > prof.get("max_atr_usd", 8.50):
                continue

            spr_pts = pb["m_spr"][idx]
            spr_px = spr_pts * pb["point"]
            spr_atr = spr_px / atr14
            if spr_pts > prof["max_spread_pts"] or spr_atr > prof["max_spr_atr"]:
                continue

            # Closed-bar HTF alignment (strictly <= bar_ts - 1 to guarantee zero lookahead)
            h1_i = int(np.searchsorted(pb["h1_time"], bar_ts, side="right")) - 1
            h4_i = int(np.searchsorted(pb["h4_time"], bar_ts, side="right")) - 1
            d1_i = int(np.searchsorted(pb["d1_time"], bar_ts, side="right")) - 1
            if min(h1_i, h4_i, d1_i) < 25:
                continue

            d1_dir = 1 if pb["d1_close"][d1_i] > pb["d1_ema20"][d1_i] else -1
            h4_dir = 1 if pb["h4_close"][h4_i] > pb["h4_ema20"][h4_i] else -1
            h1_dir = 1 if pb["h1_close"][h1_i] > pb["h1_ema20"][h1_i] else -1
            m15_dir = 1 if pb["m_close"][idx] > pb["m_ema20"][idx] else -1

            htf_sum = d1_dir + h4_dir + h1_dir
            if htf_sum >= 2 and m15_dir == 1:
                direction, dir_sign = "BUY", 1
            elif htf_sum <= -2 and m15_dir == -1:
                direction, dir_sign = "SELL", -1
            else:
                continue

            spot = pb["m_close"][idx]
            bsl_res = max(float(np.max(pb["m_high"][idx - 47 : idx + 1])), float(np.max(pb["h1_high"][h1_i - 23 : h1_i + 1])))
            ssl_sup = min(float(np.min(pb["m_low"][idx - 47 : idx + 1])), float(np.min(pb["h1_low"][h1_i - 23 : h1_i + 1])))
            rng_pct = min(100.0, max(0.0, ((spot - ssl_sup) / max(bsl_res - ssl_sup, 1e-9)) * 100.0))

            # Directional Bar-Delta & VPIN
            c_win = pb["m_close"][idx - 11 : idx + 1]
            o_win = pb["m_open"][idx - 11 : idx + 1]
            h_win = pb["m_high"][idx - 11 : idx + 1]
            l_win = pb["m_low"][idx - 11 : idx + 1]
            v_win = pb["m_vol"][idx - 11 : idx + 1]
            signed_delta = ((c_win - o_win) / np.maximum(h_win - l_win, 1e-9)) * v_win
            vol_sum = max(float(np.sum(v_win)), 1.0)
            dii = float(np.sum(signed_delta) / vol_sum)
            tvpin = float(np.mean(np.abs(signed_delta) / np.maximum(v_win, 1.0)))

            # Directional VPIN adverse-selection gate
            if (dii * dir_sign) <= -0.65:
                continue

            # ICT Structure Tag
            bull_fvg = pb["m_low"][idx - 1] > pb["m_high"][idx - 3] and pb["m_close"][idx - 2] > pb["m_close"][idx - 3]
            bear_fvg = pb["m_high"][idx - 1] < pb["m_low"][idx - 3] and pb["m_close"][idx - 2] < pb["m_close"][idx - 3]
            fvg_match = (dir_sign == 1 and bull_fvg) or (dir_sign == -1 and bear_fvg)
            ema_stack = (dir_sign == 1 and spot > pb["m_ema9"][idx] > pb["m_ema21"][idx]) or (
                dir_sign == -1 and spot < pb["m_ema9"][idx] < pb["m_ema21"][idx]
            )
            if fvg_match:
                ict_tag = "OB+IFVG"
            elif (dir_sign == 1 and rng_pct <= 38.0) or (dir_sign == -1 and rng_pct >= 62.0):
                ict_tag = "VAL-RECLAIM"
            elif ema_stack:
                ict_tag = "EMA-FLOW"
            else:
                ict_tag = "NEUTRAL"

            if ict_tag not in prof["allowed_ict"]:
                continue

            close_slice = pb["m_close"][idx - 64 : idx + 1]
            mom = compute_momentum_alpha(closes=close_slice, atr14=atr14, sleeve=sleeve)
            kf = compute_kalman_fair_value(
                closes=close_slice, atr14=atr14, sleeve=sleeve, utc_hour=dt_utc.hour, spread_price=spr_px, tvpin=tvpin
            )
            ou = compute_ou_mean_reversion(closes=close_slice, fair_value=float(kf["fair_value"]), atr14=atr14, lookback=64)

            ou_valid = bool(ou["is_valid_ou"] and ou["ou_state"] in ("PRIME_OU_SNAPBACK", "OU_STRETCHED"))
            if prof["block_noise_drift"] and mom["mom_state"] == "NOISE_DRIFT" and not ou_valid:
                continue
            if abs(float(mom["tsmom_z"])) < prof["min_abs_tsmom_z"] and ict_tag != "OB+IFVG":
                continue

            # Composite Score
            eff = abs(float(pb["m_close"][idx] - pb["m_close"][idx - 20])) / max(
                float(np.sum(np.abs(np.diff(pb["m_close"][idx - 20 : idx + 1])))), 1e-9
            )
            aligned_dii = max(0.0, dir_sign * dii)
            cronus_ml = 1.0 / (1.0 + math.exp(-((eff * 4.5) + (aligned_dii * 3.8) + 0.45 - 0.75)))

            tf_pts = ((abs(htf_sum) / 3.0) * 32.0) + 10.0
            delta_pts = min(22.0, (aligned_dii * 85.0) + (tvpin * 10.0))
            ict_pts = 20.0 if ict_tag == "OB+IFVG" else (16.0 if ict_tag == "VAL-RECLAIM" else 13.0)
            ml_pts = cronus_ml * 18.0
            kf_pts = 4.0 if (not kf["is_climax"] and not kf["mm_taxed"] and ((dir_sign == 1 and kf["regime_bias"] == "BULL_IMPULSE") or (dir_sign == -1 and kf["regime_bias"] == "BEAR_IMPULSE"))) else 0.0
            score = min(98.0, max(15.0, tf_pts + delta_pts + ict_pts + ml_pts + kf_pts))

            if mom["mom_crash_veto"]:
                continue
            if mom["is_chasing_spike"] and direction == mom["mom_dir"]:
                score *= 0.80
            elif mom["is_pullback_entry"] and direction == mom["mom_dir"]:
                score = min(99.0, score + 5.0)
            if ou["is_valid_ou"] and direction == ou["ou_dir"]:
                score = min(99.0, score + (4.5 if ou["ou_state"] == "PRIME_OU_SNAPBACK" else 2.5))

            if prof["gate"] <= score <= prof["max_score"]:
                rank_key = score + min(10.0, abs(float(mom["tsmom_z"])) * 4.0)
                candidates_scored.append((rank_key, score, direction, ict_tag, atr14, spr_px, pb))

        if candidates_scored:
            candidates_scored.sort(key=lambda x: x[0], reverse=True)
            _, score, direction, ict_tag, atr14, spr_px, pb = candidates_scored[0]
            is_buy = direction == "BUY"
            slip_px = SLIPPAGE_POINTS[sleeve] * pb["point"]
            raw_entry = pb["m_close"][idx]
            entry_px = (raw_entry + spr_px + slip_px) if is_buy else (raw_entry - slip_px)

            r_dist = atr14 * prof["sl_atr_mult"]
            tp_dist = r_dist * prof["tp_r_mult"]
            sl_px = round((entry_px - r_dist) if is_buy else (entry_px + r_dist), pb["digits"])
            tp_px = round((entry_px + tp_dist) if is_buy else (entry_px - tp_dist), pb["digits"])

            risk_usd = min(equity * prof["risk_pct"], prof["max_risk_usd"])
            loss_per_lot = (r_dist / pb["tick_sz"]) * pb["tick_val"]
            raw_lots = risk_usd / max(loss_per_lot, 1e-9)
            lots = round(max(pb["vol_min"], min(pb["vol_max"], math.floor(raw_lots / pb["vol_step"]) * pb["vol_step"])), 2)

            open_pos = {
                "bundle": pb,
                "direction": direction,
                "open_utc": dt_utc.strftime("%Y-%m-%d %H:%M"),
                "init_lots": lots,
                "rem_lots": lots,
                "entry": entry_px,
                "sl": sl_px,
                "tp": tp_px,
                "r_dist": r_dist,
                "risk_usd": risk_usd,
                "be_locked": False,
                "partial_done": False,
                "realized_partial_pnl": 0.0,
                "ict_tag": ict_tag,
                "score": round(score, 1),
            }

    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    net_pnl = equity - INITIAL_EQUITY_PER_SLEEVE

    stats = {
        "sleeve": sleeve,
        "profile": prof["name"],
        "trades": len(trades),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round((net_pnl / INITIAL_EQUITY_PER_SLEEVE) * 100.0, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "final_eq": round(equity, 2),
        "expectancy": round(net_pnl / len(trades), 2) if trades else 0.0,
    }
    return trades, stats


def main() -> None:
    print("=== SHIVSOUL NEXUS v8.0 // 2025-2026 HISTORICAL MULTI-SLEEVE BACKTEST ===")
    print(f"Window: {START_UTC.strftime('%Y-%m-%d')} -> {END_UTC.strftime('%Y-%m-%d')} | Start Capital: ${INITIAL_EQUITY_PER_SLEEVE:,.2f}/sleeve ($3,000.00 Fleet)\n")

    all_trades: list[dict] = []
    sleeve_stats: list[dict] = []

    for sleeve in ["T1", "T2", "T3"]:
        cfg = SLEEVES[sleeve]
        prof = VISION_PROFILES[sleeve]
        print(f">>> Loading MT5 History for {sleeve} (#{cfg['login']} | {prof['name']})...")
        if not mt5.initialize(path=cfg["path"], login=cfg["login"], password=cfg["password"], server=cfg["server"], timeout=60000):
            print(f"  [ERR] MT5 init failed for {sleeve}: {mt5.last_error()}")
            continue

        try:
            bundles = []
            for candidates, _ in prof["assets"]:
                b = fetch_historical_bundle(sleeve, candidates)
                if b:
                    bundles.append(b)
                    print(f"  • {b['clean_name']:<7}: {len(b['m15']):,} M15 bars loaded")
        finally:
            mt5.shutdown()

        trades, stats = simulate_sleeve(sleeve, bundles)
        all_trades.extend(trades)
        sleeve_stats.append(stats)

    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if all_trades:
        with REPORT_CSV.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(all_trades[0].keys()))
            writer.writeheader()
            writer.writerows(all_trades)

    print("\n==========================================================================================")
    print(f"{'SLEEVE':<6} | {'PROFILE':<29} | {'TRADES':>6} | {'WIN%':>6} | {'PF':>5} | {'NET PNL':>10} | {'RET%':>7} | {'MAX DD':>7}")
    print("------------------------------------------------------------------------------------------")
    tot_trades = 0
    tot_pnl = 0.0
    for st in sleeve_stats:
        tot_trades += st["trades"]
        tot_pnl += st["net_pnl"]
        print(
            f"{st['sleeve']:<6} | {st['profile']:<29} | {st['trades']:>6} | {st['win_rate']:>5.1f}% | "
            f"{st['profit_factor']:>5.2f} | ${st['net_pnl']:>+9.2f} | {st['return_pct']:>+6.1f}% | {st['max_dd_pct']:>6.2f}%"
        )
    print("------------------------------------------------------------------------------------------")
    fleet_ret = (tot_pnl / 3000.0) * 100.0
    print(f"{'FLEET':<6} | {'COMBINED 3-SLEEVE PORTFOLIO':<29} | {tot_trades:>6} | {'--':>6} | {'--':>5} | ${tot_pnl:>+9.2f} | {fleet_ret:>+6.1f}% | {'--':>7}")
    print("==========================================================================================")
    print(f"[SAVED] Full 2025-2026 trade-by-trade audit exported to: {REPORT_CSV}")


if __name__ == "__main__":
    main()
