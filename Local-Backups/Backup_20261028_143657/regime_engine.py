import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
import MetaTrader5 as mt5

# ------------------------------------------------------------------------------
# 1. High-Impact Macro Schedule (Temporal Vector)
# ------------------------------------------------------------------------------
# In production, this dictionary is updated via an MCP Economic Calendar tool or API.
# It defines windows of major releases (CPI, NFP, FOMC, Rate Decisions).
HIGH_IMPACT_EVENTS_SCHEDULE = [
    # Format: (DayOfWeek 0=Mon..4=Fri, Hour UTC, Minute UTC, Currency, EventName)
    (2, 12, 30, "USD", "CPI_INFLATION"),       # Wed 12:30 UTC
    (4, 12, 30, "USD", "NON_FARM_PAYROLLS"),   # Fri 12:30 UTC
    (2, 18, 0,  "USD", "FOMC_RATE_DECISION"),  # Wed 18:00 UTC
]

def check_temporal_news_vector(currency: str = "USD", window_minutes: int = 60) -> dict:
    """
    Evaluates whether the current UTC timestamp is within `window_minutes`
    before or after a scheduled high-impact macro economic release.
    """
    now = datetime.now(timezone.utc)
    current_dow = now.weekday()
    current_min_of_day = now.hour * 60 + now.minute

    for event_dow, event_hour, event_min, event_curr, event_name in HIGH_IMPACT_EVENTS_SCHEDULE:
        if current_dow == event_dow and currency.upper() in event_curr:
            event_total_min = event_hour * 60 + event_min
            delta_min = abs(current_min_of_day - event_total_min)
            if delta_min <= window_minutes:
                return {
                    "is_news_window": True,
                    "event_name": event_name,
                    "minutes_to_event": delta_min
                }

    return {"is_news_window": False, "event_name": "NONE", "minutes_to_event": -1}

# ------------------------------------------------------------------------------
# 2. Volatility Vector (ATR Expansion / Compression)
# ------------------------------------------------------------------------------
def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def evaluate_volatility_vector(df: pd.DataFrame) -> dict:
    atr_series = compute_atr(df, period=14)
    current_atr = atr_series.iloc[-2]
    atr_baseline_20 = atr_series.iloc[-22:-2].mean()

    # Ratio of current ATR to historical 20-period baseline
    atr_ratio = current_atr / atr_baseline_20 if atr_baseline_20 > 0 else 1.0

    if atr_ratio >= 1.35:
        state = "EXPANDING"
    elif atr_ratio <= 0.75:
        state = "COMPRESSED"
    else:
        state = "NORMAL"

    return {
        "current_atr": round(float(current_atr), 5),
        "baseline_atr": round(float(atr_baseline_20), 5),
        "atr_ratio": round(float(atr_ratio), 2),
        "volatility_state": state
    }

# ------------------------------------------------------------------------------
# 3. Directional Vector (ADX + EMA Slope)
# ------------------------------------------------------------------------------
def compute_adx(df: pd.DataFrame, period: int = 14) -> float:
    high = df['high']
    low = df['low']
    close = df['close']

    plus_dm = high.diff()
    minus_dm = low.diff()

    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), -minus_dm, 0.0)

    tr_series = compute_atr(df, period=1)
    tr_smooth = tr_series.rolling(window=period).sum()

    plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).sum() / tr_smooth)
    minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).sum() / tr_smooth)

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx = dx.rolling(window=period).mean().iloc[-2]
    return float(adx) if not np.isnan(adx) else 20.0

def evaluate_directional_vector(df: pd.DataFrame) -> dict:
    close = df['close']
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()

    adx_value = compute_adx(df, period=14)
    slope_20 = (ema_20.iloc[-2] - ema_20.iloc[-7]) / 5.0

    if adx_value >= 25.0:
        if ema_20.iloc[-2] > ema_50.iloc[-2] and slope_20 > 0:
            direction = "STRONG_TREND_BULLISH"
        elif ema_20.iloc[-2] < ema_50.iloc[-2] and slope_20 < 0:
            direction = "STRONG_TREND_BEARISH"
        else:
            direction = "TRANSITIONAL_TREND"
    else:
        direction = "RANGING_CHOP"

    return {
        "adx": round(adx_value, 1),
        "direction_state": direction
    }

# ------------------------------------------------------------------------------
# 4. Master Regime State Classifier & Quantum Score Modulator
# ------------------------------------------------------------------------------
def evaluate_market_regime(symbol: str, timeframe: int = mt5.TIMEFRAME_M15) -> dict:
    """
    Evaluates the three vectors and produces a final Market_Regime_State,
    along with max Quantum Score caps and cautionary flags.
    """
    # 1. Temporal Vector Check
    currency = symbol[:3] if "USD" not in symbol[:3] else symbol[3:6]
    news = check_temporal_news_vector(currency="USD", window_minutes=60)
    
    if news["is_news_window"]:
        return {
            "regime_state": "HIGH_VOLATILITY_NEWS",
            "score_cap": 50.0,
            "position_multiplier": 0.0,  # Prohibit entries during news spikes
            "warning": f"⚠️ Macro Blackout: {news['event_name']} within {news['minutes_to_event']}m. Execution locked.",
            "metrics": {"news": news}
        }

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 70)
    if rates is None or len(rates) < 30:
        return {
            "regime_state": "UNKNOWN_DATA_FEED_FAULT",
            "score_cap": 50.0,
            "position_multiplier": 0.5,
            "warning": "⚠️ Limited bar history. Operating with defensive constraints.",
            "metrics": {}
        }

    df = pd.DataFrame(rates)
    volatility = evaluate_volatility_vector(df)
    directional = evaluate_directional_vector(df)

    # 2. Synthesis into Final Regime State
    if directional["direction_state"] == "RANGING_CHOP" and volatility["volatility_state"] == "COMPRESSED":
        regime_state = "LOW_VOLATILITY_CHOP"
        score_cap = 65.0
        pos_mult = 0.5
        warning = "⚠️ Market Regime: Compressed Chop. Expect false breakouts. Max score capped at 65."
    elif "STRONG_TREND" in directional["direction_state"]:
        regime_state = directional["direction_state"]
        score_cap = 98.0
        pos_mult = 1.0
        warning = "🟢 Market Regime: High-Momentum Trend. Institutional SMC confluences valid."
    elif volatility["volatility_state"] == "EXPANDING":
        regime_state = "VOLATILITY_EXPANSION_UNCERTAIN"
        score_cap = 75.0
        pos_mult = 0.75
        warning = "🟡 Market Regime: Expanding Volatility without Trend Confluence. Maintain strict SL."
    else:
        regime_state = "STANDARD_CONSOLIDATION"
        score_cap = 80.0
        pos_mult = 0.8
        warning = "ℹ️ Market Regime: Standard Volume Range. Standard risk rules apply."

    return {
        "regime_state": regime_state,
        "score_cap": score_cap,
        "position_multiplier": pos_mult,
        "warning": warning,
        "metrics": {
            "atr_ratio": volatility["atr_ratio"],
            "adx": directional["adx"],
            "volatility": volatility["volatility_state"],
            "directional": directional["direction_state"]
        }
    }

def modulate_quantum_score(raw_score: float, regime: dict) -> float:
    """
    Applies the regime hard-cap to the raw Quantum Score.
    """
    return min(float(raw_score), float(regime["score_cap"]))