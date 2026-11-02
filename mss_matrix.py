from smt_engine import evaluate_smt_divergence
import datetime
# ==============================================================================
# ICT KILLZONE SESSION FILTER (INSTITUTIONAL LIQUIDITY WINDOWS)
# ==============================================================================

def audit_ict_killzone(symbol: str = "") -> dict:
    """
    Evaluates whether the current UTC time falls within an active ICT institutional Killzone:
    - London Open Killzone  : 07:00 - 10:00 UTC
    - New York Open Killzone: 12:00 - 15:00 UTC
    - London Close Killzone : 15:00 - 17:00 UTC
    All other hours are classified as CHOP / OFF_SESSION.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cur_hour = now_utc.hour + (now_utc.minute / 60.0)

    # 1. London Open Killzone (07:00 - 10:00 UTC)
    if 7.0 <= cur_hour < 10.0:
        return {"in_killzone": True, "session": "LONDON_OPEN", "time_utc": now_utc.strftime("%H:%M UTC")}

    # 2. New York Open Killzone (12:00 - 15:00 UTC)
    elif 12.0 <= cur_hour < 15.0:
        return {"in_killzone": True, "session": "NEW_YORK_OPEN", "time_utc": now_utc.strftime("%H:%M UTC")}

    # 3. London Close Killzone (15:00 - 17:00 UTC)
    elif 15.0 <= cur_hour < 17.0:
        return {"in_killzone": True, "session": "LONDON_CLOSE", "time_utc": now_utc.strftime("%H:%M UTC")}

    # Off-Session (Asian Range / Dead Zones)
    else:
        return {
            "in_killzone": False,
            "session": "OFF_SESSION_CHOP",
            "time_utc": now_utc.strftime("%H:%M UTC"),
            "reason": f"Off-Session ({now_utc.strftime('%H:%M UTC')}): Outside London/NY Killzones"
        }

from macro_sentinel import fetch_macro_freeze_status
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

def detect_swing_points(df, window=3):
    """Identifies institutional fractal swing highs and swing lows."""
    df['swing_high'] = False
    df['swing_low'] = False
    for i in range(window, len(df) - window):
        if df['high'].iloc[i] == df['high'].iloc[i - window : i + window + 1].max():
            df.loc[df.index[i], 'swing_high'] = True
        if df['low'].iloc[i] == df['low'].iloc[i - window : i + window + 1].min():
            df.loc[df.index[i], 'swing_low'] = True
    return df

def audit_htf_order_block(symbol):
    """Evaluates H1 Dealing Range and identifies nearest unmitigated OB / Sweep."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 48)
    if rates is None or len(rates) < 20:
        return {"h1_bias": "NEUTRAL", "h1_zone": "INSUFFICIENT_DATA", "h1_sweep": False}
    
    df = pd.DataFrame(rates)
    df = detect_swing_points(df, window=2)
    cur_price = df['close'].iloc[-1]
    
    recent_high = df[df['swing_high']]['high'].tail(3).max() if any(df['swing_high']) else df['high'].max()
    recent_low = df[df['swing_low']]['low'].tail(3).min() if any(df['swing_low']) else df['low'].min()
    
    # Equilibrium & Premium/Discount
    eq = (recent_high + recent_low) / 2.0
    h1_bias = "DISCOUNT (BULLISH ACCUMULATION)" if cur_price < eq else "PREMIUM (BEARISH DISTRIBUTION)"
    
    # High/Low Sweep detection on last 2 candles
    h1_sweep_high = df['high'].iloc[-2:].max() >= recent_high
    h1_sweep_low = df['low'].iloc[-2:].min() <= recent_low
    h1_sweep = "LIQUIDITY SWEPT (BSL)" if h1_sweep_high else ("LIQUIDITY SWEPT (SSL)" if h1_sweep_low else "NONE")
    
    return {
        "h1_bias": h1_bias,
        "h1_range": f"{recent_low:.5f} - {recent_high:.5f}",
        "h1_sweep": h1_sweep,
        "cur_price": cur_price
    }

def audit_ltf_mss(symbol, timeframe, tf_name="M5"):
    """Scans for Market Structure Shift (displacement breaking fractal swing)."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 30)
    if rates is None or len(rates) < 15:
        return {"tf": tf_name, "mss_state": "STANDBY", "disp": 0.0}
    
    df = pd.DataFrame(rates)
    df = detect_swing_points(df, window=2)
    
    last_candle = df.iloc[-1]
    prev_swings_high = df[df['swing_high']]['high']
    prev_swings_low = df[df['swing_low']]['low']
    
    mss_state = "⚖️ RANGE BOUND"
    if not prev_swings_high.empty:
        last_sh = prev_swings_high.iloc[-1]
        # Bullish MSS: Close above previous swing high
        if last_candle['close'] > last_sh:
            mss_state = f"🟢 BULLISH MSS (+SH {last_sh:.5f})"
            
    if not prev_swings_low.empty:
        last_sl = prev_swings_low.iloc[-1]
        # Bearish MSS: Close below previous swing low
        if last_candle['close'] < last_sl:
            mss_state = f"🔴 BEARISH MSS (-SL {last_sl:.5f})"
            
    # Calculate body displacement
    body_size = abs(last_candle['close'] - last_candle['open'])
    avg_body = abs(df['close'] - df['open']).mean()
    disp = round(body_size / (avg_body if avg_body > 0 else 0.0001), 1)
    
    return {
        "tf": tf_name,
        "mss_state": mss_state,
        "displacement_mult": disp
    }

def get_multi_tf_matrix(symbols=['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']):
    results = []
    for s in symbols:
        h1 = audit_htf_order_block(s)
        m5 = audit_ltf_mss(s, mt5.TIMEFRAME_M5, "M5")
        m1 = audit_ltf_mss(s, mt5.TIMEFRAME_M1, "M1")
        
        # Confluence check: H1 Bias aligned with M5 and M1 MSS
        is_aligned = False
        if "BULLISH" in h1['h1_bias'] and "BULLISH" in m5['mss_state'] and "BULLISH" in m1['mss_state']:
            is_aligned = True
            readiness = "🎯 FULL CONFLUENCE LONG"
        elif "BEARISH" in h1['h1_bias'] and "BEARISH" in m5['mss_state'] and "BEARISH" in m1['mss_state']:
            is_aligned = True
            readiness = "🎯 FULL CONFLUENCE SHORT"
        elif "LIQUIDITY SWEPT" in h1['h1_sweep']:
            readiness = f"⚡ {h1['h1_sweep']} (HUNTING M1 MSS)"
        else:
            readiness = "Scanning Liquidity"
            
        results.append({
            "Symbol": s,
            "Price": round(h1.get('cur_price', 0.0), 5),
            "H1 Zone Bias": h1['h1_bias'],
            "H1 Sweep Event": h1['h1_sweep'],
            "M5 Intermediate Structure": m5['mss_state'],
            "M1 Micro MSS": m1['mss_state'],
            "M1 Displacement": f"{m1['displacement_mult']}x ATR",
            "Execution Confluence": readiness
        })
    return pd.DataFrame(results)

if __name__ == "__main__":
    if mt5.initialize():
        df_mat = get_multi_tf_matrix()
        print(df_mat.to_string())
        mt5.shutdown()


def audit_fvg_imbalance(symbol, timeframe=mt5.TIMEFRAME_M5):
    """Detects 3-candle Fair Value Gap (imbalance) on the execution timeframe."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 5)
    if rates is None or len(rates) < 4:
        return {"fvg_type": "NONE", "fvg_gap": 0.0, "fvg_top": 0.0, "fvg_bottom": 0.0}
    
    # 3-candle sequence: c1, c2 (displacement), c3
    c1, c2, c3 = rates[-3], rates[-2], rates[-1]
    
    # Bullish FVG: Low of candle 3 is above High of candle 1
    if c3['low'] > c1['high']:
        return {
            "fvg_type": "BULLISH_FVG",
            "fvg_gap": round(c3['low'] - c1['high'], 5),
            "fvg_top": c3['low'],
            "fvg_bottom": c1['high']
        }
    # Bearish FVG: High of candle 3 is below Low of candle 1
    elif c3['high'] < c1['low']:
        return {
            "fvg_type": "BEARISH_FVG",
            "fvg_gap": round(c1['low'] - c3['high'], 5),
            "fvg_top": c1['low'],
            "fvg_bottom": c3['high']
        }
    return {"fvg_type": "NONE", "fvg_gap": 0.0, "fvg_top": 0.0, "fvg_bottom": 0.0}

def audit_rejection_order_block(symbol, timeframe=mt5.TIMEFRAME_M5):
    """Finds the most recent unmitigated Order Block / Rejection Block candle."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 15)
    if rates is None or len(rates) < 6:
        return {"ob_type": "NONE", "ob_price": 0.0}
    
    # Scan backward for opposite-color candle prior to expansion
    for i in range(len(rates) - 2, 2, -1):
        candle = rates[i]
        next_candle = rates[i + 1]
        # Bullish OB: Bearish candle followed by strong bullish displacement
        if candle['close'] < candle['open'] and next_candle['close'] > candle['high']:
            return {"ob_type": "BULLISH_OB", "ob_price": float(candle['low']), "ob_level": float(candle['open'])}
        # Bearish OB: Bullish candle followed by strong bearish displacement
        elif candle['close'] > candle['open'] and next_candle['close'] < candle['low']:
            return {"ob_type": "BEARISH_OB", "ob_price": float(candle['high']), "ob_level": float(candle['open'])}
            
    return {"ob_type": "NONE", "ob_price": 0.0}

def evaluate_ict_setup(symbol: str) -> dict:
    """
    Institutional Confluence Pipeline:
    1. H4 Trend & Bias Context (analyze_higher_timeframe_context)
    2. H1 Dealing Range & Equilibrium (audit_htf_order_block)
    3. Institutional Turtle Soup Sweep (detect_institutional_liquidity_grab)
    4. M5 Market Structure Shift & Displacement (audit_ltf_mss)
    5. M5 Fair Value Gap (audit_fvg_imbalance) & Order Block (audit_rejection_order_block)
    6. Sovereign Apex Red-Team Veto Gate (run_red_team_validation)
    """
    htf = analyze_higher_timeframe_context(symbol)
    h1 = audit_htf_order_block(symbol)
    m5_mss = audit_ltf_mss(symbol, mt5.TIMEFRAME_M5, "M5")
    fvg = audit_fvg_imbalance(symbol, mt5.TIMEFRAME_M5)
    ob = audit_rejection_order_block(symbol, mt5.TIMEFRAME_M5)
    liq_grab = detect_institutional_liquidity_grab(symbol, htf.get("h4_bias", "NEUTRAL"))

    cur_p = float(h1.get('cur_price', 0.0))
    is_discount = "DISCOUNT" in h1.get('h1_bias', '')
    is_premium = "PREMIUM" in h1.get('h1_bias', '')
    bullish_mss = "BULLISH" in m5_mss.get('mss_state', '')
    bearish_mss = "BEARISH" in m5_mss.get('mss_state', '')

    # Setup candidate formulation
    valid_buy = (is_discount or liq_grab.get("type") == "SSL_SWEEP_BULLISH") and (bullish_mss or fvg.get('fvg_type') == 'BULLISH_FVG')
    valid_sell = (is_premium or liq_grab.get("type") == "BSL_SWEEP_BEARISH") and (bearish_mss or fvg.get('fvg_type') == 'BEARISH_FVG')

    sl = 0.0
    tp = 0.0
    signal = None

    if valid_buy:
        sl = float(ob['ob_price']) if ob.get('ob_price', 0) > 0 and ob['ob_price'] < cur_p else float(fvg.get('fvg_bottom', cur_p * 0.998))
        risk = cur_p - sl
        if risk > 0:
            tp = cur_p + (risk * 2.2)
            signal = "BUY"
        else:
            valid_buy = False

    elif valid_sell:
        sl = float(ob['ob_price']) if ob.get('ob_price', 0) > 0 and ob['ob_price'] > cur_p else float(fvg.get('fvg_top', cur_p * 1.002))
        risk = sl - cur_p
        if risk > 0:
            tp = cur_p - (risk * 2.2)
            signal = "SELL"
        else:
            valid_sell = False

    # Red-Team Veto Gate Evaluation
    vetoed = False
    veto_reason = "No Setup"

    if signal in ["BUY", "SELL"]:
        vetoed, veto_reason = run_red_team_validation(symbol, signal, cur_p, sl, htf_data=htf)

    is_valid = (signal is not None) and (not vetoed)

    return {
        "symbol": symbol,
        "signal": signal if is_valid else None,
        "valid": is_valid,
        "vetoed": vetoed,
        "veto_reason": veto_reason,
        "h4_bias": htf.get("h4_bias", "NEUTRAL"),
        "zone": "DISCOUNT" if is_discount else ("PREMIUM" if is_premium else "EQ"),
        "sweep": liq_grab.get("type") if liq_grab.get("detected") else h1.get('h1_sweep', 'NONE'),
        "mss": m5_mss.get('mss_state', 'STANDBY'),
        "fvg": fvg.get('fvg_type', 'NONE'),
        "entry": cur_p,
        "sl": sl,
        "tp": tp
    }

# ==============================================================================
# SOVEREIGN APEX V4.1: RED-TEAM VETO GATE & INSTITUTIONAL LIQUIDITY ENGINE
# Extracted directly from production commit 146fee8~1
# ==============================================================================

def analyze_higher_timeframe_context(symbol: str) -> dict:
    try:
        rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 50)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)

        h4_bias = "NEUTRAL"
        m15_resistance = 0.0
        m15_support = 0.0

        if rates_h4 is not None and len(rates_h4) >= 25:
            closes_h4 = [r['close'] for r in rates_h4]
            ema20_h4 = sum(closes_h4[-20:]) / 20
            ema50_h4 = sum(closes_h4[-50:]) / 50 if len(closes_h4) >= 50 else ema20_h4
            if ema20_h4 > ema50_h4:
                h4_bias = "BULLISH_EXPANSION"
            elif ema20_h4 < ema50_h4:
                h4_bias = "BEARISH_EXPANSION"

        if rates_m15 is not None and len(rates_m15) >= 20:
            highs_m15 = [r['high'] for r in rates_m15]
            lows_m15 = [r['low'] for r in rates_m15]
            m15_resistance = max(highs_m15[-15:])
            m15_support = min(lows_m15[-15:])

        return {
            "h4_bias": h4_bias,
            "m15_res": round(float(m15_resistance), 5),
            "m15_sup": round(float(m15_support), 5),
            "status": "ONLINE"
        }
    except Exception:
        return {"h4_bias": "NEUTRAL", "m15_res": 0.0, "m15_sup": 0.0, "status": "OFFLINE"}


def detect_institutional_liquidity_grab(symbol: str, htf_bias: str) -> dict:
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 35)
        if rates is not None and len(rates) >= 25:
            hist_highs = [r['high'] for r in rates[-25:-2]]
            hist_lows  = [r['low'] for r in rates[-25:-2]]
            bsl_pool = max(hist_highs)
            ssl_pool = min(hist_lows)

            prev_bar = rates[-2]
            curr_bar = rates[-1]

            # SSL Grab (Bullish Turtle Soup)
            if prev_bar['low'] < ssl_pool and prev_bar['close'] > ssl_pool:
                if htf_bias in ["BULLISH_EXPANSION", "NEUTRAL"]:
                    return {
                        "detected": True,
                        "type": "SSL_SWEEP_BULLISH",
                        "action": "BUY",
                        "sweep_wick": float(prev_bar['low']),
                        "reclaim_level": float(ssl_pool),
                        "target_pool": float(bsl_pool),
                        "desc": f"SSL Swept ({prev_bar['low']:.4f} < {ssl_pool:.4f}) & Reclaimed"
                    }

            # BSL Grab (Bearish Turtle Soup)
            if prev_bar['high'] > bsl_pool and prev_bar['close'] < bsl_pool:
                if htf_bias in ["BEARISH_EXPANSION", "NEUTRAL"]:
                    return {
                        "detected": True,
                        "type": "BSL_SWEEP_BEARISH",
                        "action": "SELL",
                        "sweep_wick": float(prev_bar['high']),
                        "reclaim_level": float(bsl_pool),
                        "target_pool": float(ssl_pool),
                        "desc": f"BSL Swept ({prev_bar['high']:.4f} > {bsl_pool:.4f}) & Reclaimed"
                    }
    except Exception:
        pass
    return {"detected": False, "type": "NONE", "desc": "No Liquidity Sweep"}


def run_red_team_validation(symbol: str, signal: str, entry: float, sl: float, htf_data: dict = None) -> tuple[bool, str]:
    """
    Sovereign Apex Red-Team Veto Gate:
    1. ICT Killzone Session Gate (Blocks off-session churn on FX/Metals)
    2. Macro Economic Sentinel (Blocks USD high-impact release windows)
    3. Structural Spread & Wick Validation
    """
    # Gate 0: ICT Killzone Filter (Exempt 24/7 crypto like BTC)
    kz = audit_ict_killzone(symbol)
    if not kz.get("in_killzone", False) and "BTC" not in symbol:
        return True, f"Killzone Veto: {kz.get('reason', 'Off-Session')}"

    # Gate 1: Macro News Sentinel Freeze
    try:
        from macro_sentinel import fetch_macro_freeze_status
        frozen, news_reason = fetch_macro_freeze_status(30)
        if frozen:
            return True, f"Macro News Freeze: {news_reason}"
    except Exception:
        pass

    # Gate 2: Structural Spread vs Risk Gate
    try:
        tick = mt5.symbol_info_tick(symbol)
        sym_info = mt5.symbol_info(symbol)
        if tick and sym_info:
            spread = (tick.ask - tick.bid)
            risk = abs(entry - sl)
            if risk > 0 and (spread / risk) > 0.20:
                return True, f"Spread Friction Veto: Spread is >20% of risk distance"
    except Exception:
        pass

    return False, "APPROVED"


# ==============================================================================
# ICT PD ARRAY MATRIX: TIER 2 (BREAKER BLOCK) & TIER 3 (LIQUIDITY VOID)
# ==============================================================================

def audit_breaker_block(symbol: str, timeframe=mt5.TIMEFRAME_M5) -> dict:
    """
    Tier 2 PD Array: Breaker Block
    Bullish Breaker: Prior swing high candle that was swept (liquidity grab),
    followed by aggressive upward displacement breaking above that high.
    The candle that formed the initial high now flips into support.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 40)
        if rates is None or len(rates) < 25:
            return {"detected": False, "type": "NONE"}

        highs = [r['high'] for r in rates]
        lows = [r['low'] for r in rates]
        closes = [r['close'] for r in rates]
        opens = [r['open'] for r in rates]

        cur_price = closes[-1]

        # Scan for Bearish Breaker (Swing Low -> Swept -> Broken down)
        for i in range(len(rates) - 15, len(rates) - 4):
            # Candidate down-candle before sweep
            if closes[i] < opens[i]:
                low_level = lows[i]
                # Did price sweep lower?
                subsequent_lows = lows[i+1:i+6]
                if subsequent_lows and min(subsequent_lows) < low_level:
                    # Did price aggressively break back below that level?
                    if cur_price < low_level:
                        return {
                            "detected": True,
                            "type": "BEARISH_BREAKER",
                            "level_top": max(opens[i], closes[i]),
                            "level_bottom": low_level,
                            "desc": f"Bearish Breaker Block at {low_level:.4f} (flips to resistance)"
                        }

        # Scan for Bullish Breaker (Swing High -> Swept -> Broken up)
        for i in range(len(rates) - 15, len(rates) - 4):
            # Candidate up-candle before sweep
            if closes[i] > opens[i]:
                high_level = highs[i]
                # Did price sweep higher?
                subsequent_highs = highs[i+1:i+6]
                if subsequent_highs and max(subsequent_highs) > high_level:
                    # Did price aggressively break back above that level?
                    if cur_price > high_level:
                        return {
                            "detected": True,
                            "type": "BULLISH_BREAKER",
                            "level_top": high_level,
                            "level_bottom": min(opens[i], closes[i]),
                            "desc": f"Bullish Breaker Block at {high_level:.4f} (flips to support)"
                        }
    except Exception:
        pass
    return {"detected": False, "type": "NONE"}


def audit_liquidity_void(symbol: str, timeframe=mt5.TIMEFRAME_M5) -> dict:
    """
    Tier 3 PD Array: Liquidity Void
    Detects extreme multi-candle one-sided runaway expansion where price traded
    inefficiently, leaving a draw on liquidity back to its 50% Consequent Encroachment.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 25)
        if rates is None or len(rates) < 10:
            return {"detected": False, "type": "NONE"}

        # Scan the last 3-6 bars for continuous non-overlapping candle bodies (voids)
        for i in range(len(rates) - 4, len(rates) - 1):
            c1, c2, c3 = rates[i-2], rates[i-1], rates[i]
            
            # Bullish expansion void (strong buyers, empty sell-side delivery)
            if c1['close'] > c1['open'] and c2['close'] > c2['open'] and c3['close'] > c3['open']:
                span = c3['high'] - c1['low']
                body_ratio = (abs(c1['close']-c1['open']) + abs(c2['close']-c2['open']) + abs(c3['close']-c3['open'])) / (span if span > 0 else 1.0)
                if body_ratio > 0.75:
                    mid_ce = (c3['high'] + c1['low']) / 2.0
                    return {
                        "detected": True,
                        "type": "BULLISH_LIQUIDITY_VOID",
                        "void_high": float(c3['high']),
                        "void_low": float(c1['low']),
                        "consequent_encroachment": float(mid_ce),
                        "desc": f"Bullish Void [{c1['low']:.2f} - {c3['high']:.2f}] CE: {mid_ce:.2f}"
                    }

            # Bearish expansion void (heavy institutional sell imbalance)
            if c1['close'] < c1['open'] and c2['close'] < c2['open'] and c3['close'] < c3['open']:
                span = c1['high'] - c3['low']
                body_ratio = (abs(c1['open']-c1['close']) + abs(c2['open']-c2['close']) + abs(c3['open']-c3['close'])) / (span if span > 0 else 1.0)
                if body_ratio > 0.75:
                    mid_ce = (c1['high'] + c3['low']) / 2.0
                    return {
                        "detected": True,
                        "type": "BEARISH_LIQUIDITY_VOID",
                        "void_high": float(c1['high']),
                        "void_low": float(c3['low']),
                        "consequent_encroachment": float(mid_ce),
                        "desc": f"Bearish Void [{c3['low']:.2f} - {c1['high']:.2f}] CE: {mid_ce:.2f}"
                    }
    except Exception:
        pass
    
    # --- Tier 8 Confluence: ICT SMT Divergence Boost ---
    smt_info = {"divergence": "NONE", "boost": 0}
    try:
        if symbol in ["EURUSD", "GBPUSD"]:
            smt_info = evaluate_smt_divergence("EURUSD", "GBPUSD")
        elif symbol in ["USDJPY", "XAUUSD"]:
            smt_info = evaluate_smt_divergence(symbol, "XAUUSD" if symbol == "USDJPY" else "USDJPY")
        
        # Apply edge boost if SMT aligns with signal
        if signal == "BUY" and smt_info.get("divergence") == "BULLISH_SMT":
            edge_score = min(95, edge_score + smt_info.get("boost", 15))
        elif signal == "SELL" and smt_info.get("divergence") == "BEARISH_SMT":
            edge_score = min(95, edge_score + smt_info.get("boost", 15))
    except Exception:
        pass

    return {"detected": False, "type": "NONE"}
