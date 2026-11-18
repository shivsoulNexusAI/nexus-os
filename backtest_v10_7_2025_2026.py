# -*- coding: utf-8 -*-
"""
QUANT-NEXUS v10.7 + V2.1 M5 HYBRID BACKTESTER (2025-01-01 to 2026-11-18)
Upgrades tested:
1. T3 XAUUSD & T1 BTCUSD full M5 history pull (copy_rates_from + copy_rates_from_pos fallback)
2. BTCUSD spread ceiling calibrated to 2500 pts ($25.00 on 2-digit quotes)
3. London/NY active impulse window (07:00-20:00 UTC) + Volatility Expansion (ATR > ATR_SMA20) + EMA Trend Separation
4. T2 FX risk-calibrated 0.03L sizing (0.3% risk per trade on $1,000 sleeve)
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
            {"base": "BTCUSD", "lot": 0.01, "max_spread_pts": 2500, "all_hours": True},
            {"base": "US30",   "lot": 0.01, "max_spread_pts": 450,  "all_hours": False},
        ],
    },
    {
        "key": "T2",
        "name": "Pending FX (Majors)",
        "login": 278062039,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_Pending_278041169\terminal64.exe",
        "symbols": [
            {"base": "EURUSD", "lot": 0.03, "max_spread_pts": 20, "all_hours": False},
            {"base": "GBPUSD", "lot": 0.03, "max_spread_pts": 22, "all_hours": False},
            {"base": "USDJPY", "lot": 0.03, "max_spread_pts": 22, "all_hours": False},
            {"base": "AUDUSD", "lot": 0.03, "max_spread_pts": 22, "all_hours": False},
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
            {"base": "XAUUSD", "lot": 0.01, "max_spread_pts": 280, "all_hours": False},
        ],
    },
]

def resolve_symbol(base: str):
    for cand in (base, base + "m", base + ".a", base + ".raw"):
        info = mt5.symbol_info(cand)
        if info is not None:
            mt5.symbol_select(cand, True)
            probe = mt5.copy_rates_from_pos(cand, mt5.TIMEFRAME_M5, 0, 50)
            if probe is not None and len(probe) > 0:
                return cand, info
    # Fallback: scan MarketWatch for any matching prefix
    for s in (mt5.symbols_get() or []):
        if s.name.upper().startswith(base.upper()):
            mt5.symbol_select(s.name, True)
            probe = mt5.copy_rates_from_pos(s.name, mt5.TIMEFRAME_M5, 0, 50)
            if probe is not None and len(probe) > 0:
                return s.name, mt5.symbol_info(s.name)
    return None, None

def fetch_m5_history(sym: str, start_utc: datetime, end_utc: datetime):
    mt5.symbol_select(sym, True)
    mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 1000)
    _t.sleep(0.35)

    start_ts = int(start_utc.timestamp())
    end_ts = int(end_utc.timestamp())
    cursor = datetime(end_utc.year, end_utc.month, end_utc.day, end_utc.hour, end_utc.minute)
    chunks = []

    for _ in range(8):
        batch = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M5, cursor, 50000)
        if batch is None or len(batch) == 0:
            break
        chunks.append(batch)
        oldest_ts = int(batch[0]["time"])
        if oldest_ts <= start_ts:
            break
        dt_prev = datetime.fromtimestamp(oldest_ts - 300, tz=timezone.utc)
        cursor = datetime(dt_prev.year, dt_prev.month, dt_prev.day, dt_prev.hour, dt_prev.minute)
        _t.sleep(0.25)

    if not chunks:
        pos_batch = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 100000)
        if pos_batch is not None and len(pos_batch) > 0:
            chunks.append(pos_batch)

    if not chunks:
        return []

    merged = {}
    for ch in reversed(chunks):
        for r in ch:
            ts = int(r["time"])
            if start_ts <= ts <= end_ts:
                merged[ts] = r
    return [merged[k] for k in sorted(merged.keys())]

def simulate_symbol(sym: str, info, rates, lot: float, max_spread_pts: int, all_hours: bool, is_t3_gold: bool):
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
    if n < 60:
        return None

    closes = [float(r["close"]) for r in rates]
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

    ema9 = [0.0] * n
    ema21 = [0.0] * n
    k9, k21 = 2.0 / 10.0, 2.0 / 22.0
    ema9[0] = closes[0]
    ema21[0] = closes[0]
    for i in range(1, n):
        ema9[i] = closes[i] * k9 + ema9[i - 1] * (1.0 - k9)
        ema21[i] = closes[i] * k21 + ema21[i - 1] * (1.0 - k21)

    for i in range(40, n):
        dt = datetime.fromtimestamp(times[i], tz=timezone.utc)
        day_key = (dt.year, dt.month, dt.day)
        if day_key != cur_day:
            cur_day = day_key
            day_start_eq = balance
            halted_today = False

        h, l, c = highs[i], lows[i], closes[i]
        sp_pts = spreads[i]
        sp_px = sp_pts * point

        # 1. Manage open position (V2.1 3-Tier Exit + Rollover Guard)
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

                # Tier 1: +1.00R BE Lock (+0.20R cushion)
                if r_mult >= 1.00 and not pos["be_locked"]:
                    cushion = max(sp_px, 0.20 * pos["init_risk"])
                    new_sl = round(pos["entry"] + cushion if is_buy else pos["entry"] - cushion, digits)
                    if (is_buy and new_sl > pos["sl"]) or (not is_buy and new_sl < pos["sl"]):
                        pos["sl"] = new_sl
                        pos["be_locked"] = True
                        be_locks += 1

                # Tier 2: +1.60R 50% Partial Harvest
                if r_mult >= 1.60 and not pos["partial_done"]:
                    harvest_px = pos["entry"] + 1.60 * pos["init_risk"] if is_buy else pos["entry"] - 1.60 * pos["init_risk"]
                    part_pnl = ((harvest_px - pos["entry"]) if is_buy else (pos["entry"] - harvest_px)) * usd_per_price_unit * 0.50
                    pos["realized_pnl"] += part_pnl
                    pos["rem_frac"] = 0.50
                    pos["partial_done"] = True
                    balance += part_pnl
                    partials += 1

                # Tier 3: >= +1.50R M5 2-Bar Structural Trail
                if r_mult >= 1.50:
                    if is_buy:
                        cand = round(min(lows[i - 1], lows[i]) - sp_px, digits)
                        if cand > pos["sl"] and cand < c:
                            pos["sl"] = cand
                    else:
                        cand = round(max(highs[i - 1], highs[i]) + sp_px, digits)
                        if cand < pos["sl"] and cand > c:
                            pos["sl"] = cand

                # T3 Pre-Rollover XAUUSD Guard (21:45 - 21:57 UTC)
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

        # 4. Check Pending Stop Order Fill / 15-Min (3-Bar) TTL Expiry
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

        # 5. Session & Volatility Expansion Gate (v10.7 quality upgrade)
        in_session = all_hours or (7 <= dt.hour <= 20)
        if not in_session:
            pending = None
            continue

        if pos is None and pending is None and sp_pts <= max_spread_pts:
            atr = atr14[i]
            atr_baseline = sum(atr14[i - 19 : i + 1]) / 20.0
            if atr <= 0 or atr < (0.95 * atr_baseline):
                continue

            ema_sep = abs(ema9[i] - ema21[i])
            if ema_sep < (0.22 * atr):
                continue

            swing_hi = max(highs[i - 6 : i])
            swing_lo = min(lows[i - 6 : i])
            box_h = swing_hi - swing_lo
            bull = ema9[i] > ema21[i] and ema9[i] > ema9[i - 1]
            bear = ema9[i] < ema21[i] and ema9[i] < ema9[i - 1]

            # Immediate M5 Impulse Breakout Strike
            if bull and c > swing_hi and (c - lows[i]) > 0.60 * atr:
                entry = round(c + sp_px, digits)
                risk = max(1.25 * atr, 3.0 * sp_px)
                pos = {
                    "side": "BUY", "entry": entry,
                    "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                    "init_risk": risk, "rem_frac": 1.0, "realized_pnl": 0.0,
                    "be_locked": False, "partial_done": False,
                }
            elif bear and c < swing_lo and (highs[i] - c) > 0.60 * atr:
                entry = round(c, digits)
                risk = max(1.25 * atr, 3.0 * sp_px)
                pos = {
                    "side": "SELL", "entry": entry,
                    "sl": round(entry + risk, digits), "tp": round(entry - 2.2 * risk, digits),
                    "init_risk": risk, "rem_frac": 1.0, "realized_pnl": 0.0,
                    "be_locked": False, "partial_done": False,
                }
            # Armed 15m TTL Pending Breakout Stop Bracket (0.25x - 3.25x ATR box)
            elif 0.25 * atr <= box_h <= 3.25 * atr:
                buf = 0.18 * atr
                if bull and swing_lo < c <= swing_hi:
                    entry = round(swing_hi + buf + sp_px, digits)
                    risk = max(1.20 * atr, 3.0 * sp_px)
                    pending = {
                        "side": "BUY", "entry": entry,
                        "sl": round(entry - risk, digits), "tp": round(entry + 2.2 * risk, digits),
                        "bar_idx": i,
                    }
                elif bear and swing_lo <= c < swing_hi:
                    entry = round(swing_lo - buf, digits)
                    risk = max(1.20 * atr, 3.0 * sp_px)
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
    print(" QUANT-NEXUS v10.7 CALIBRATED M5 HYBRID BACKTEST (London/NY Expansion + Volatility Gate | 2025-2026)")
    print("=====================================================================================================")

    fleet_trades = 0
    fleet_net = 0.0

    for s in SLEEVES:
        if not mt5.initialize(path=s["path"], login=s["login"], password=s["password"], server=s["server"], portable=False):
            print(f"[{s['key']}] MT5 Init failed: {mt5.last_error()}")
            continue

        print(f"\n>>> SLEEVE {s['key']}: {s['name']} (#{s['login']})")
        for scfg in s["symbols"]:
            sym, info = resolve_symbol(scfg["base"])
            if not sym:
                print(f"  - {scfg['base']}: Symbol unavailable on terminal")
                continue
            rates = fetch_m5_history(sym, START_UTC, END_UTC)
            if len(rates) < 100:
                print(f"  - {sym}: Insufficient M5 bars returned ({len(rates)})")
                continue

            res = simulate_symbol(
                sym, info, rates, scfg["lot"], scfg["max_spread_pts"],
                scfg["all_hours"], is_t3_gold=(s["key"] == "T3")
            )
            if not res:
                continue

            fleet_trades += res["trades"]
            fleet_net += res["net_pnl"]
            print(
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
