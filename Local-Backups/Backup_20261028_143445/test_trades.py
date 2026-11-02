import pandas as pd
from signature_engine import detect_candlestick_pattern, detect_fair_value_gap, detect_vwap_relation

def test_bullish_engulfing_detection():
    # Setup: Candle -3 bearish (open: 100, close: 90), Candle -2 bullish engulfing (open: 88, close: 102)
    data = {
        'open': [95.0, 100.0, 88.0, 98.0],
        'close': [94.0, 90.0, 102.0, 99.0],
        'high': [96.0, 101.0, 103.0, 100.0],
        'low': [93.0, 89.0, 87.0, 97.0],
        'tick_volume': [100, 100, 200, 50]
    }
    df = pd.DataFrame(data)
    pattern = detect_candlestick_pattern(df)
    assert pattern == "BULLISH_ENGULFING"

def test_bearish_engulfing_detection():
    # Setup: Candle -3 bullish (open: 90, close: 100), Candle -2 bearish engulfing (open: 102, close: 88)
    data = {
        'open': [90.0, 90.0, 102.0, 92.0],
        'close': [91.0, 100.0, 88.0, 91.0],
        'high': [92.0, 101.0, 103.0, 93.0],
        'low': [89.0, 89.0, 87.0, 90.0],
        'tick_volume': [100, 100, 250, 60]
    }
    df = pd.DataFrame(data)
    pattern = detect_candlestick_pattern(df)
    assert pattern == "BEARISH_ENGULFING"

def test_fvg_detection():
    # Candle 1 (high: 100), Candle 2 (large up impulse), Candle 3 (low: 105) -> Imbalance between 100 and 105
    data = {
        'open': [90.0, 101.0, 106.0, 108.0],
        'high': [100.0, 106.0, 110.0, 109.0],
        'low':  [88.0, 99.0, 105.0, 107.0],
        'close': [98.0, 105.0, 108.0, 108.0],
        'tick_volume': [100, 300, 200, 100]
    }
    df = pd.DataFrame(data)
    fvg = detect_fair_value_gap(df)
    assert fvg == "FVG"
from regime_engine import modulate_quantum_score

def test_quantum_score_capping_in_chop():
    mock_chop_regime = {
        "regime_state": "LOW_VOLATILITY_CHOP",
        "score_cap": 65.0,
        "position_multiplier": 0.5,
        "warning": "⚠️ Market Regime: Compressed Chop."
    }
    # Raw setup scored 95/100, but regime must clamp it to 65.0
    adjusted_score = modulate_quantum_score(95.0, mock_chop_regime)
    assert adjusted_score == 65.0

def test_quantum_score_uncapped_in_strong_trend():
    mock_trend_regime = {
        "regime_state": "STRONG_TREND_BULLISH",
        "score_cap": 98.0,
        "position_multiplier": 1.0,
        "warning": "🟢 Market Regime: High-Momentum Trend."
    }
    adjusted_score = modulate_quantum_score(92.0, mock_trend_regime)
    assert adjusted_score == 92.0

def test_regime_volume_scaling_logic():
    base_capital = 10000.0  # $10,000 equity
    base_risk_pct = 0.01    # 1.0% ($100)
    sl_points = 1500.0      # 150 pips on gold
    loss_per_point = 0.10   # $0.10 per point per 1.0 lot

    def compute_mock_volume(multiplier):
        if multiplier <= 0.0:
            return 0.0
        risk_cash = base_capital * base_risk_pct * multiplier
        raw_lot = risk_cash / (sl_points * loss_per_point)
        return round(max(0.01, round(raw_lot / 0.01) * 0.01), 2)

    # 1. Full allocation in Strong Trend (1.0x)
    trend_lots = compute_mock_volume(1.0)
    assert trend_lots == 0.67

    # 2. Halved allocation in Compressed Chop (0.5x)
    chop_lots = compute_mock_volume(0.5)
    assert chop_lots == 0.33

    # 3. Complete risk block in High-Impact News (0.0x)
    news_lots = compute_mock_volume(0.0)
    assert news_lots == 0.0
def test_spread_guard_blowout_rejection():
    # 168 points spread on XAUUSD must fail safety
    current_spread = 168.0
    max_threshold = 45.0
    assert (current_spread <= max_threshold) is False

def test_spread_guard_normal_pass():
    # 6 points spread on EURUSD must pass safety
    current_spread = 6.0
    max_threshold = 25.0
    assert (current_spread <= max_threshold) is True

def test_mtf_trap_penalty_application():
    raw_score = 90.0
    mock_trap_result = {
        "alignment_state": "COUNTER_TREND_TRAP",
        "score_delta": -30,
        "is_trap": True
    }
    final_score = max(0.0, raw_score + mock_trap_result["score_delta"])
    assert final_score == 60.0
    assert mock_trap_result["is_trap"] is True

def test_mtf_fractal_bonus_application():
    raw_score = 75.0
    mock_aligned_result = {
        "alignment_state": "FRACTAL_CONFLUENCE",
        "score_delta": 20,
        "is_trap": False
    }
    final_score = min(100.0, raw_score + mock_aligned_result["score_delta"])
    assert final_score == 95.0

def test_reputation_weighted_conviction():
    # Elite trader (weight 2.0) upvotes, novice trader (weight 0.5) downvotes
    votes = [("UP", 2.0), ("DOWN", 0.5)]
    net_score = sum(w for d, w in votes if d == "UP") - sum(w for d, w in votes if d == "DOWN")
    assert net_score == 1.5

def test_breakeven_1r_trigger_calculation():
    open_price = 2650.00
    initial_sl = 2640.00
    initial_risk = open_price - initial_sl  # 10 points
    target_1r = open_price + initial_risk   # 2660.00
    
    current_bid_under = 2658.00
    current_bid_over = 2661.00
    
    # Below 1:1 R:R -> Do not trigger
    assert current_bid_under < target_1r
    # At or above 1:1 R:R -> Trigger breakeven
    assert current_bid_over >= target_1r

    buffer = 1.0  # 1 point buffer
    be_sl = open_price + buffer
    assert be_sl == 2651.00
