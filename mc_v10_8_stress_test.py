# -*- coding: utf-8 -*-
"""
QUANT-NEXUS v10.8 MONTE CARLO DRAWDOWN & TAIL-RISK STRESS TEST (1,000 ITERATIONS)
Evaluates pruned positive-expectancy roster:
- T1: BTCUSD (0.01L) + US30 (0.01L)
- T2: GBPUSD (0.05L, Sweep Reclaim)
- T3: XAUUSD (0.01L, Hybrid Gold)
"""
import random
import MetaTrader5 as mt5
import backtest_v10_8_2025_2026 as bt

ITERATIONS = 1000
SEED = 20261118
POSITIVE_SET = {"BTCUSD", "US30", "GBPUSD", "XAUUSD"}

def extract_trade_series(sym: str, info, rates, lot: float, max_spread_pts: int, all_hours: bool, mode: str, is_t3_gold: bool):
    """Runs v10.8 bar simulation and returns the exact list of realized per-trade PnLs."""
    point = float(info.point)
    digits = int(info.digits)
    tick_val = float(info.trade_tick_value) if info.trade_tick_value > 0 else 1.0
    tick_size = float(info.trade_tick_size) if info.trade_tick_size > 0 else point
    usd_per_price_unit = (tick_val / tick_size) * lot

    balance = 1000.0
    day_start_eq = 1000.0
    cur_day = None
    halted_today = False
    pos = None
    pending = None
    trades = []

    n = len(rates)
    closes = [float(r["close"]) for r in rates]
    opens = [float(r["open"]) for r in rates]
    highs = [float(r["high"]) for r in rates]
    lows = [float(r["low"]) for r in rates]
    spreads = [int(r["spread"]) for r in rates]
    times = [int(r["time"]) for r in rates]

    trs = [0.0] * n
    for i in range(1, n):
        trs[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    atr14 = [0.0] * n
    for i in range(14, n):
        atr14[i] = sum(trs[i - 13 : i + 1]) / 14.0

    ema9, ema21, ema60, ema150 = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
    k9, k21, k60, k150 = 2.0 / 10.0, 2.0 / 22.0, 2.0 / 61.0, 2.0 / 151.0
    ema9[0] = ema21[0] = ema60[0] = ema150[0] = closes[0]
    for i in range(1, n):
        ema9[i] = closes[i] * k9 + ema9[i - 1] * (1.0 - k9)
        ema21[i] = closes[i] * k21 + ema21[i - 1] * (1.0 - k21)
        ema60[i] = closes[i] * k60 + ema60[i - 1] * (1.0 - k60)
        ema150[i] = closes[i] * k150 + ema150[i - 1] * (1.0 - k150)

    from datetime import datetime, timezone
    for i in range(160, n):
        dt = datetime.fromtimestamp(times[i], tz=timezone.utc)
        day_key = (dt.year, dt.month, dt.day)
        if day_key != cur_day:
            cur_day = day_key
            day_start_eq = balance
            halted_today = False

        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        sp_pts = spreads[i]
        sp_px = sp_pts * point

        if pos is not None:
            is_buy = pos["side"] == "BUY"
            hit_sl = (l <= pos["sl"]) if is_buy else (h >= pos["sl"])
            hit_tp = (h >= pos["tp"]) if is_buy else (l <= pos["tp"])

            if hit_sl:
                pnl_rem = ((pos["sl"] - pos["entry"]) if is_buy else (pos["entry"] - pos["sl"])) * usd_per_price_unit * pos["rem_frac"]
                balance += pnl_rem
                trades.append(pos["realized_pnl"] + pnl_rem)
                pos = None
            elif hit_tp:
                pnl_rem = ((pos["tp"] - pos["entry"]) if is_buy else (pos["entry"] - pos["tp"])) * usd_per_price_unit * pos["rem_frac"]
                balance += pnl_rem
                trades.append(pos["realized_pnl"] + pnl_rem)
                pos = None
            else:
                best_px = h if is_buy else l
                gain = (best_px - pos["entry"]) if is_buy else (pos["entry"] - best_px)
                r_mult = gain / pos["init_risk"] if pos["init_risk"] > 0 else 0.0

                if r_mult >= 1.00 and not pos["be_locked"]:
                    cushion = max(sp_px, 0.20 * pos["init_risk"])
                    new_sl = round(pos["entry"] + cushion if is_buy else pos["entry"] - cushion, digits)
                    if (is_buy and new_sl > pos["sl"]) or (not is_buy and new_sl < pos["sl"]):
                        pos["sl"] = new_sl
                        pos["be_locked"] = True

                if r_mult >= 1.60 and not pos["partial_done"]:
                    harvest_px = pos["entry"] + 1.60 * pos["init_risk"] if is_buy else pos["entry"] - 1.60 * pos["init_risk"]
                    part_pnl = ((harvest_px - pos["entry"]) if is_buy else (pos["entry"] - harvest_px)) * usd_per_price_unit * 0.50
                    pos["realized_pnl"] += part_pnl
                    pos["rem_frac"] = 0.50
                    pos["partial_done"] = True
                    balance += part_pnl

                if r_mult >= 1.50:
                    if is_buy:
                        cand = round(min(lows[i - 1], lows[i]) - sp_px, digits)
                        if cand > pos["sl"] and cand < c:
                            pos["sl"] = cand
                    else:
                        cand = round(max(highs[i - 1], highs[i]) + sp_px, digits)
                        if cand < pos["sl"] and cand > c:
                            pos["sl"] = cand

                if pos is not None and is_t3_gold and dt.hour == 21 and 45 <= dt.minute <= 57:
                    cur_gain = (c - pos["entry"]) if is_buy else (pos["entry"] - c)
                    if cur_gain > sp_px:
                        be_sl = round(pos["entry"] + sp_px if is_buy else pos["entry"] - sp_px, digits)
                        if (is_buy and be_sl > pos["sl"]) or (not is_buy and be_sl < pos["sl"]):
                            pos["sl"] = be_sl
                    else:
                        pnl_rem = cur_gain * usd_per_price_unit * pos["rem_frac"]
                        balance += pnl_rem
                        trades.append(pos["realized_pnl"] + pnl_rem)
                        pos = None

        float_pnl = 0.0
        if pos is not None:
            is_buy = pos["side"] == "BUY"
            float_pnl = ((c - pos["entry"]) if is_buy else (pos["entry"] - c)) * usd_per_price_unit * pos["rem_frac"]
        eq_now = balance + float_pnl

        if not halted_today and eq_now <= (day_start_eq * 0.96):
            halted_today = True
            pending = None
            if pos is not None:
                balance += float_pnl
                trades.append(pos["realized_pnl"] + float_pnl)
                pos = None
            continue

        if halted_today:
            continue

        if (dt.hour == 21 and dt.minute >= 45) or dt.hour in (22, 23) or (dt.hour == 0 and dt.minute < 15):
            pending = None
            continue

        if pending is not None and pos is None:
            if (i - pending["bar_idx"]) > 3:
                pending = None
            else:
                if pending["side"] == "BUY" and h >= pending["entry"]:
                    pos = {
                        "side": "BUY", "entry": pending["entry"], "sl": pending["sl"], "tp": pending["tp"],
                        "init_risk": abs(pending["entry"] - pending["sl"]), "rem_frac": 1.0, "realized_pnl": 0.0,
                        "be_locked": False, "partial_done": False,
                    }
                    pending = None
                elif pending["side"] == "SELL" and l <= pending["entry"]:
                    pos = {
                        "side": "SELL", "entry": pending["entry"], "sl": pending["sl"], "tp": pending["tp"],
                        "init_risk": abs(pending["sl"] - pending["entry"]), "rem_frac": 1.0, "realized_pnl": 0.0,
                        "be_locked": False, "partial_done": False,
                    }
                    pending = None

        in_session = all_hours or (7 <= dt.hour <= 20)
        if not in_session:
            pending = None
            continue

        if pos is None and pending is None and sp_pts <= max_spread_pts:
            atr = atr14[i]
            if atr <= 0 or atr < (5.0 * sp_px):
                continue

            htf_bull = ema60[i] > ema150[i] and ema60[i] > ema60[i - 3]
            htf_bear = ema60[i] < ema150[i] and ema60[i] < ema60[i - 3]
            swing_hi = max(highs[i - 8 : i])
            swing_lo = min(lows[i - 8 : i])
            box_h = swing_hi - swing_lo

            if mode == "SWEEP_RECLAIM":
                if htf_bull and l < swing_lo and c > swing_lo and c > o and (c - l) > 0.55 * (h - l):
                    entry = round(c + sp_px, digits)
                    risk = max(entry - (l - 0.25 * atr), 1.25 * atr, 6.0 * sp_px)
                    pos = {
                        "side": "BUY", "entry": entry,
                        "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                        "init_risk": risk, "rem_frac": 1.0, "realized_pnl": 0.0,
                        "be_locked": False, "partial_done": False,
                    }
                elif htf_bear and h > swing_hi and c < swing_hi and c < o and (h - c) > 0.55 * (h - l):
                    entry = round(c, digits)
                    risk = max((h + 0.25 * atr) - entry, 1.25 * atr, 6.0 * sp_px)
                    pos = {
                        "side": "SELL", "entry": entry,
                        "sl": round(entry + risk, digits), "tp": round(entry - 2.2 * risk, digits),
                        "init_risk": risk, "rem_frac": 1.0, "realized_pnl": 0.0,
                        "be_locked": False, "partial_done": False,
                    }
            else:
                bull = htf_bull and ema9[i] > ema21[i]
                bear = htf_bear and ema9[i] < ema21[i]
                if bull and c > swing_hi and (c - l) > 0.60 * atr:
                    entry = round(c + sp_px, digits)
                    risk = max(1.30 * atr, 6.0 * sp_px)
                    pos = {
                        "side": "BUY", "entry": entry,
                        "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                        "init_risk": risk, "rem_frac": 1.0, "realized_pnl": 0.0,
                        "be_locked": False, "partial_done": False,
                    }
                elif bear and c < swing_lo and (h - c) > 0.60 * atr:
                    entry = round(c, digits)
                    risk = max(1.30 * atr, 6.0 * sp_px)
                    pos = {
                        "side": "SELL", "entry": entry,
                        "sl": round(entry + risk, digits), "tp": round(entry - 2.2 * risk, digits),
                        "init_risk": risk, "rem_frac": 1.0, "realized_pnl": 0.0,
                        "be_locked": False, "partial_done": False,
                    }
                elif 0.25 * atr <= box_h <= 3.25 * atr:
                    buf = 0.18 * atr
                    if bull and swing_lo < c <= swing_hi:
                        entry = round(swing_hi + buf + sp_px, digits)
                        risk = max(1.25 * atr, 6.0 * sp_px)
                        pending = {
                            "side": "BUY", "entry": entry,
                            "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                            "bar_idx": i,
                        }
                    elif bear and swing_lo <= c < swing_hi:
                        entry = round(swing_lo - buf, digits)
                        risk = max(1.25 * atr, 6.0 * sp_px)
                        pending = {
                            "side": "SELL", "entry": entry,
                            "sl": round(entry + risk, digits), "tp": round(entry - 2.2 * risk, digits),
                            "bar_idx": i,
                        }
    return trades

def run_monte_carlo(trades: list[float], start_cap: float, iterations: int = 1000, seed: int = 2026):
    rng = random.Random(seed)
    n = len(trades)
    max_dds = []
    final_pnls = []
    min_equities = []

    for _ in range(iterations):
        # Bootstrap resample with replacement to simulate adverse losing-streak clustering
        sample = rng.choices(trades, k=n)
        eq = start_cap
        peak = start_cap
        max_dd = 0.0
        min_eq = start_cap
        for pnl in sample:
            eq += pnl
            if eq > peak:
                peak = eq
            if eq < min_eq:
                min_eq = eq
            dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        max_dds.append(max_dd)
        final_pnls.append(eq - start_cap)
        min_equities.append(min_eq)

    max_dds.sort()
    final_pnls.sort()
    min_equities.sort()

    def pct(arr, q):
        idx = min(int(q * len(arr)), len(arr) - 1)
        return arr[idx]

    prob_profit = sum(1 for x in final_pnls if x > 0) / iterations * 100.0
    return {
        "n_trades": n,
        "med_pnl": pct(final_pnls, 0.50),
        "p05_pnl": pct(final_pnls, 0.05),
        "p95_pnl": pct(final_pnls, 0.95),
        "med_dd": pct(max_dds, 0.50),
        "p95_dd": pct(max_dds, 0.95),
        "p99_dd": pct(max_dds, 0.99),
        "p05_min_eq": pct(min_equities, 0.05),
        "prob_profit": prob_profit,
    }

def main():
    print("=====================================================================================================")
    print(" QUANT-NEXUS v10.8 MONTE CARLO STRESS TEST (1,000 Bootstrap Resamples | Pruned Positive Roster)")
    print("=====================================================================================================")

    trade_map = {}
    gold_done = False

    for s in bt.SLEEVES:
        if not mt5.initialize(path=s["path"], login=s["login"], password=s["password"], server=s["server"], portable=False):
            continue
        for scfg in s["symbols"]:
            if scfg["base"] not in POSITIVE_SET:
                continue
            sym, info, rates = bt.resolve_and_fetch(scfg["base"], bt.START_UTC, bt.END_UTC)
            if not sym or len(rates) < 200:
                continue
            t_list = extract_trade_series(
                sym, info, rates, scfg["lot"], scfg["max_spread_pts"],
                scfg["all_hours"], scfg["mode"], is_t3_gold=(s["key"] == "T3")
            )
            trade_map[scfg["base"]] = t_list
            if scfg["base"] == "XAUUSD":
                gold_done = True
        mt5.shutdown()

    if not gold_done:
        t1 = bt.SLEEVES[0]
        if mt5.initialize(path=t1["path"], login=t1["login"], password=t1["password"], server=t1["server"], portable=False):
            sym, info, rates = bt.resolve_and_fetch("XAUUSD", bt.START_UTC, bt.END_UTC)
            if sym and len(rates) >= 200:
                trade_map["XAUUSD"] = extract_trade_series(sym, info, rates, 0.01, 280, False, "HYBRID_GOLD", True)
            mt5.shutdown()

    print("\n--- 1. PER-SYMBOL MONTE CARLO ($1,000 Starting Capital per Symbol) ---")
    for idx, sym in enumerate(["XAUUSD", "US30", "BTCUSD", "GBPUSD"]):
        t_list = trade_map.get(sym, [])
        if not t_list:
            print(f"  • {sym:<8}: No trade data")
            continue
        mc = run_monte_carlo(t_list, 1000.0, ITERATIONS, SEED + idx)
        print(
            f"  • {sym:<8} ({mc['n_trades']:>4}T) | MedDD: {mc['med_dd']:>5.2f}% | "
            f"95%ile DD: {mc['p95_dd']:>5.2f}% | 99%ile DD: {mc['p99_dd']:>5.2f}% | "
            f"MedNet: ${mc['med_pnl']:>+7.2f} | 5%ile Net: ${mc['p05_pnl']:>+7.2f} | "
            f"P(Profit): {mc['prob_profit']:>5.1f}%"
        )

    # Combined $3,000 Fleet Portfolio (T1 $1k + T2 $1k + T3 $1k)
    all_trades = []
    for sym in ["XAUUSD", "US30", "BTCUSD", "GBPUSD"]:
        all_trades.extend(trade_map.get(sym, []))

    if all_trades:
        fleet_mc = run_monte_carlo(all_trades, 3000.0, ITERATIONS, SEED + 99)
        print("\n--- 2. COMBINED 3-TERMINAL FLEET MONTE CARLO ($3,000 Combined Capital) ---")
        print(f"  • Total Trades Resampled : {fleet_mc['n_trades']} trades across XAUUSD, US30, BTCUSD, GBPUSD")
        print(f"  • Median Max Drawdown    : {fleet_mc['med_dd']:.2f}% (${3000.0 * fleet_mc['med_dd'] / 100.0:.2f})")
        print(f"  • 95th-Percentile Max DD : {fleet_mc['p95_dd']:.2f}% (${3000.0 * fleet_mc['p95_dd'] / 100.0:.2f})")
        print(f"  • 99th-Percentile Max DD : {fleet_mc['p99_dd']:.2f}% (${3000.0 * fleet_mc['p99_dd'] / 100.0:.2f})")
        print(f"  • Median Net PnL         : ${fleet_mc['med_pnl']:+.2f} (5th %ile: ${fleet_mc['p05_pnl']:+.2f} | 95th %ile: ${fleet_mc['p95_pnl']:+.2f})")
        print(f"  • Probability of Profit  : {fleet_mc['prob_profit']:.1f}%")
    print("=====================================================================================================")

if __name__ == "__main__":
    main()
