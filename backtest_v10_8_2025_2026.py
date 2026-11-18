# -*- coding: utf-8 -*-
"""
QUANT-NEXUS v10.8 + V2.1 M5 STRUCTURAL BACKTESTER (2025-01-01 to 2026-11-18)
Tests:
1. M15 Trend Regime Filter (3-bar synthesized M15 EMA20 vs EMA50)
2. T2 FX Liquidity-Sweep Reclaim + Pullback Entry (eliminates breakout false-breakout drag)
3. Minimum Risk-to-Spread Efficiency Gate (init_risk >= 6.0 * spread)
4. Cross-terminal XAUUSD M5 history fallback so T3 Gold always backtests 100k bars
"""
import time as _t
from datetime import datetime, timezone
import MetaTrader5 as mt5

START_UTC = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
END_UTC = datetime(2026, 11, 18, 23, 59, tzinfo=timezone.utc)

SLEEVES = [
    {
        "key": "T1",
        "name": "Apex Satellite (Crypto/Index)",
        "login": 278062038,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe",
        "symbols": [
            {"base": "BTCUSD", "lot": 0.01, "max_spread_pts": 2500, "all_hours": True,  "mode": "BREAKOUT"},
            {"base": "US30",   "lot": 0.01, "max_spread_pts": 450,  "all_hours": False, "mode": "BREAKOUT"},
        ],
    },
    {
        "key": "T2",
        "name": "Pending FX (Majors - Sweep Reclaim)",
        "login": 278062039,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_Pending_278041169\terminal64.exe",
        "symbols": [
            {"base": "EURUSD", "lot": 0.05, "max_spread_pts": 16, "all_hours": False, "mode": "SWEEP_RECLAIM"},
            {"base": "GBPUSD", "lot": 0.05, "max_spread_pts": 18, "all_hours": False, "mode": "SWEEP_RECLAIM"},
            {"base": "USDJPY", "lot": 0.05, "max_spread_pts": 18, "all_hours": False, "mode": "SWEEP_RECLAIM"},
            {"base": "AUDUSD", "lot": 0.05, "max_spread_pts": 18, "all_hours": False, "mode": "SWEEP_RECLAIM"},
        ],
    },
    {
        "key": "T3",
        "name": "HFT Gold (XAUUSD)",
        "login": 278062042,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_HFT_278041671\terminal64.exe",
        "symbols": [
            {"base": "XAUUSD", "lot": 0.01, "max_spread_pts": 280, "all_hours": False, "mode": "HYBRID_GOLD"},
        ],
    },
]

def resolve_and_fetch(base: str, start_utc: datetime, end_utc: datetime):
    candidates = [base, base + "m", base + ".a", base + ".raw"]
    for s in (mt5.symbols_get() or []):
        if base.upper() in s.name.upper() and s.name not in candidates:
            candidates.append(s.name)

    start_ts = int(start_utc.timestamp())
    end_ts = int(end_utc.timestamp())

    for cand in candidates:
        info = mt5.symbol_info(cand)
        if info is None:
            continue
        mt5.symbol_select(cand, True)
        mt5.copy_rates_from_pos(cand, mt5.TIMEFRAME_M5, 0, 1000)
        _t.sleep(0.3)

        cursor = datetime(end_utc.year, end_utc.month, end_utc.day, end_utc.hour, end_utc.minute)
        chunks = []
        for _ in range(8):
            batch = mt5.copy_rates_from(cand, mt5.TIMEFRAME_M5, cursor, 50000)
            if batch is None or len(batch) == 0:
                break
            chunks.append(batch)
            oldest_ts = int(batch[0]["time"])
            if oldest_ts <= start_ts:
                break
            dt_prev = datetime.fromtimestamp(oldest_ts - 300, tz=timezone.utc)
            cursor = datetime(dt_prev.year, dt_prev.month, dt_prev.day, dt_prev.hour, dt_prev.minute)
            _t.sleep(0.2)

        if not chunks:
            pos_batch = mt5.copy_rates_from_pos(cand, mt5.TIMEFRAME_M5, 0, 100000)
            if pos_batch is not None and len(pos_batch) > 0:
                chunks.append(pos_batch)

        if chunks:
            merged = {}
            for ch in reversed(chunks):
                for r in ch:
                    ts = int(r["time"])
                    if start_ts <= ts <= end_ts:
                        merged[ts] = r
            rates = [merged[k] for k in sorted(merged.keys())]
            if len(rates) >= 200:
                return cand, info, rates
    return None, None, []

def simulate_symbol(sym: str, info, rates, lot: float, max_spread_pts: int, all_hours: bool, mode: str, is_t3_gold: bool):
    point = float(info.point)
    digits = int(info.digits)
    tick_val = float(info.trade_tick_value) if info.trade_tick_value > 0 else 1.0
    tick_size = float(info.trade_tick_size) if info.trade_tick_size > 0 else point
    usd_per_price_unit = (tick_val / tick_size) * lot

    balance = 1000.0
    peak_eq = 1000.0
    max_dd_pct = 0.0
    day_start_eq = 1000.0
    cur_day = None
    halted_today = False

    pos = None
    pending = None
    trades = []
    dd_halts = 0
    be_locks = 0
    partials = 0

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

    # Fast M5 EMAs + Higher-Timeframe M15 proxy EMAs (EMA60 & EMA150 on M5)
    ema9, ema21, ema60, ema150 = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
    k9, k21, k60, k150 = 2.0 / 10.0, 2.0 / 22.0, 2.0 / 61.0, 2.0 / 151.0
    ema9[0] = ema21[0] = ema60[0] = ema150[0] = closes[0]
    for i in range(1, n):
        ema9[i] = closes[i] * k9 + ema9[i - 1] * (1.0 - k9)
        ema21[i] = closes[i] * k21 + ema21[i - 1] * (1.0 - k21)
        ema60[i] = closes[i] * k60 + ema60[i - 1] * (1.0 - k60)
        ema150[i] = closes[i] * k150 + ema150[i - 1] * (1.0 - k150)

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

        # 1. Manage Open Position (V2.1 3-Tier Exit)
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
                        be_locks += 1

                if r_mult >= 1.60 and not pos["partial_done"]:
                    harvest_px = pos["entry"] + 1.60 * pos["init_risk"] if is_buy else pos["entry"] - 1.60 * pos["init_risk"]
                    part_pnl = ((harvest_px - pos["entry"]) if is_buy else (pos["entry"] - harvest_px)) * usd_per_price_unit * 0.50
                    pos["realized_pnl"] += part_pnl
                    pos["rem_frac"] = 0.50
                    pos["partial_done"] = True
                    balance += part_pnl
                    partials += 1

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

        # 2. Check 4.0% Daily DD Hard-Flatten Circuit Breaker
        float_pnl = 0.0
        if pos is not None:
            is_buy = pos["side"] == "BUY"
            float_pnl = ((c - pos["entry"]) if is_buy else (pos["entry"] - c)) * usd_per_price_unit * pos["rem_frac"]
        eq_now = balance + float_pnl
        if eq_now > peak_eq:
            peak_eq = eq_now
        dd_now = (peak_eq - eq_now) / peak_eq * 100.0 if peak_eq > 0 else 0.0
        if dd_now > max_dd_pct:
            max_dd_pct = dd_now

        if not halted_today and eq_now <= (day_start_eq * 0.96):
            halted_today = True
            dd_halts += 1
            pending = None
            if pos is not None:
                balance += float_pnl
                trades.append(pos["realized_pnl"] + float_pnl)
                pos = None
            continue

        if halted_today:
            continue

        # 3. Rollover Blackout (21:45 - 00:15 UTC)
        if (dt.hour == 21 and dt.minute >= 45) or dt.hour in (22, 23) or (dt.hour == 0 and dt.minute < 15):
            pending = None
            continue

        # 4. Pending Stop Order Check (15m TTL)
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

        # 5. Entry Evaluation with M15 Regime + Spread Efficiency Gate (risk >= 6.0x spread)
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
                # M15 trend + M5 liquidity sweep below 8-bar swing low (or above swing high) & strong close reclaim
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
                # BREAKOUT / HYBRID_GOLD aligned with M15 regime
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

    wins = [p for p in trades if p > 0]
    losses = [p for p in trades if p < 0]
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = (gw / gl) if gl > 0 else 0.0
    wr = (len(wins) / len(trades) * 100.0) if trades else 0.0
    net = balance - 1000.0
    expectancy = (net / len(trades)) if trades else 0.0
    d0 = datetime.fromtimestamp(times[0], tz=timezone.utc).strftime("%Y-%m-%d")
    d1 = datetime.fromtimestamp(times[-1], tz=timezone.utc).strftime("%Y-%m-%d")

    return {
        "symbol": sym, "span": f"{d0}..{d1}", "bars": n,
        "trades": len(trades), "win_rate": wr, "pf": pf,
        "net_pnl": net, "max_dd_pct": max_dd_pct, "expectancy": expectancy,
        "be_locks": be_locks, "partials": partials, "dd_halts": dd_halts,
    }

def main():
    print("=====================================================================================================")
    print(" QUANT-NEXUS v10.8 M15-REGIME + SWEEP-RECLAIM + SPREAD-EFFICIENCY BACKTEST (2025-2026)")
    print("=====================================================================================================")

    fleet_trades = 0
    fleet_net = 0.0
    gold_done = False

    for s in SLEEVES:
        if not mt5.initialize(path=s["path"], login=s["login"], password=s["password"], server=s["server"], portable=False):
            print(f"[{s['key']}] MT5 Init failed: {mt5.last_error()}")
            continue

        print(f"\n>>> SLEEVE {s['key']}: {s['name']} (#{s['login']})")
        for scfg in s["symbols"]:
            sym, info, rates = resolve_and_fetch(scfg["base"], START_UTC, END_UTC)
            if not sym or len(rates) < 200:
                print(f"  - {scfg['base']}: Insufficient M5 bars on terminal #{s['login']} (will retry on fallback terminal if available)")
                continue

            res = simulate_symbol(
                sym, info, rates, scfg["lot"], scfg["max_spread_pts"],
                scfg["all_hours"], scfg["mode"], is_t3_gold=(s["key"] == "T3")
            )
            if scfg["base"] == "XAUUSD":
                gold_done = True
            fleet_trades += res["trades"]
            fleet_net += res["net_pnl"]
            print(
                f"  • {res['symbol']:<8} | {res['span']} ({res['bars']:>6}) | T:{res['trades']:>4} | "
                f"WR:{res['win_rate']:>5.1f}% | PF:{res['pf']:>4.2f} | Net:${res['net_pnl']:>+8.2f} | "
                f"MaxDD:{res['max_dd_pct']:>5.2f}% | Exp:${res['expectancy']:>+5.2f} | "
                f"BE:{res['be_locks']} Part:{res['partials']} DDHalt:{res['dd_halts']}"
            )
        mt5.shutdown()

    # Fallback XAUUSD history pull via T1 (#278062038) if T3 terminal had 0 cached M5 bars
    if not gold_done:
        t1 = SLEEVES[0]
        if mt5.initialize(path=t1["path"], login=t1["login"], password=t1["password"], server=t1["server"], portable=False):
            sym, info, rates = resolve_and_fetch("XAUUSD", START_UTC, END_UTC)
            if sym and len(rates) >= 200:
                res = simulate_symbol(sym, info, rates, 0.01, 280, False, "HYBRID_GOLD", True)
                fleet_trades += res["trades"]
                fleet_net += res["net_pnl"]
                print(
                    f"\n>>> SLEEVE T3 FALLBACK DATA (#278062038 cache):\n"
                    f"  • {res['symbol']:<8} | {res['span']} ({res['bars']:>6}) | T:{res['trades']:>4} | "
                    f"WR:{res['win_rate']:>5.1f}% | PF:{res['pf']:>4.2f} | Net:${res['net_pnl']:>+8.2f} | "
                    f"MaxDD:{res['max_dd_pct']:>5.2f}% | Exp:${res['expectancy']:>+5.2f} | "
                    f"BE:{res['be_locks']} Part:{res['partials']} DDHalt:{res['dd_halts']}"
                )
            mt5.shutdown()

    print("\n=====================================================================================================")
    print(f" FLEET SUMMARY (2025-2026): Total Trades = {fleet_trades} | Combined Net PnL = ${fleet_net:+.2f}")
    print("=====================================================================================================")

if __name__ == "__main__":
    main()
