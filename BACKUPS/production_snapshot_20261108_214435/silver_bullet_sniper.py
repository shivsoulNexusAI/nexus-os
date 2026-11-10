r"""
QuantNexus Alpha Engine: Hardened ICT Silver Bullet Model
Liquidity Sweep Pre-condition (BSL/SSL Purge), Displacement, ATR Filter, 50% MT & Buffer SL
Account: 278017866 | Directory: C:\Quant-Nexus-Eng
"""

import math
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

# Institutional Silver Bullet Delivery Windows (UTC)
KILLZONES = [
    ("LONDON_OPEN", 7, 0, 8, 0),    # 07:00 – 08:00 UTC
    ("NY_AM",       14, 0, 15, 0),  # 14:00 – 15:00 UTC
    ("NY_PM",       19, 0, 20, 0),  # 19:00 – 20:00 UTC
]

# Tuned Entry Profile
DISPLACEMENT_BODY_RATIO = 0.70     # Body >= 70% of candle range
MIN_ATR_MULTIPLIER      = 0.30     # FVG gap >= 0.30 * ATR(14)
MIN_RR_RATIO            = 2.0      # Minimum 1:2 Risk-to-Reward
SPREAD_BUFFER_MULT      = 1.0      # Invalidation buffer = 1.0x spread
SWEEP_LOOKBACK_BARS     = 20       # Lookback window for BSL/SSL pools

@dataclass
class LiquiditySweep:
    pool_type: str          # 'BSL' (Buy-Side) or 'SSL' (Sell-Side)
    level: float
    sweep_candle_time: int
    penetration_pts: float

@dataclass
class FVG:
    direction: str          # 'BULLISH' or 'BEARISH'
    top: float
    bottom: float
    gap_size: float
    mean_threshold: float   # 50% Consequent Encroachment / MT
    creation_time: datetime
    mitigated: bool = False

@dataclass
class SilverBulletSetup:
    symbol: str
    direction: str          # 'BUY' or 'SELL'
    entry_price: float      # 50% Mean Threshold
    stop_loss: float        # Displacement swing + spread buffer
    take_profit: float      # >= 1:2 R:R target
    risk_reward: float
    killzone: str
    displacement_ratio: float
    fvg: FVG
    sweep: LiquiditySweep

def check_killzone(utc_now: Optional[datetime] = None) -> Tuple[bool, str]:
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    
    current_minutes = utc_now.hour * 60 + utc_now.minute
    for name, sh, sm, eh, em in KILLZONES:
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if start_min <= current_minutes < end_min:
            return True, name
    return False, "OUT_OF_KILLZONE"

def calculate_atr(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    
    trs = []
    for i in range(1, len(candles)):
        c_curr = candles[i]
        c_prev = candles[i - 1]
        tr = max(
            c_curr['high'] - c_curr['low'],
            abs(c_curr['high'] - c_prev['close']),
            abs(c_curr['low'] - c_prev['close'])
        )
        trs.append(tr)
    
    return sum(trs[-period:]) / period

def detect_displacement(open_p: float, high_p: float, low_p: float, close_p: float) -> Tuple[bool, float, str]:
    rng = high_p - low_p
    if rng <= 1e-6:
        return False, 0.0, "NEUTRAL"
    
    body = abs(close_p - open_p)
    ratio = body / rng
    is_displaced = ratio >= DISPLACEMENT_BODY_RATIO
    direction = "BULLISH" if close_p > open_p else "BEARISH"
    return is_displaced, ratio, direction

def find_active_fvg(candles: List[Dict], atr_val: float = 0.0) -> Optional[FVG]:
    if len(candles) < 3:
        return None
    
    c0 = candles[-3]
    c1 = candles[-2]
    c2 = candles[-1]
    
    displaced, _, dir_c1 = detect_displacement(c1['open'], c1['high'], c1['low'], c1['close'])
    if not displaced:
        return None
    
    min_gap = (MIN_ATR_MULTIPLIER * atr_val) if atr_val > 0 else 0.0
    
    # Bullish FVG: Low of C2 > High of C0
    if dir_c1 == "BULLISH" and c2['low'] > c0['high']:
        gap = c2['low'] - c0['high']
        if gap >= min_gap:
            top = c2['low']
            bottom = c0['high']
            mt = bottom + (gap * 0.50)
            return FVG(
                direction="BULLISH",
                top=top,
                bottom=bottom,
                gap_size=gap,
                mean_threshold=mt,
                creation_time=datetime.now(timezone.utc)
            )
            
    # Bearish FVG: High of C2 < Low of C0
    if dir_c1 == "BEARISH" and c2['high'] < c0['low']:
        gap = c0['low'] - c2['high']
        if gap >= min_gap:
            top = c0['low']
            bottom = c2['high']
            mt = bottom + (gap * 0.50)
            return FVG(
                direction="BEARISH",
                top=top,
                bottom=bottom,
                gap_size=gap,
                mean_threshold=mt,
                creation_time=datetime.now(timezone.utc)
            )
            
    return None

def detect_liquidity_sweep(candles: List[Dict], lookback: int = SWEEP_LOOKBACK_BARS) -> Optional[LiquiditySweep]:
    """
    Identifies if the recent price action swept prior structural liquidity:
    - BSL Sweep: High of C1 or C2 punctured the lookback swing high before turning down.
    - SSL Sweep: Low of C1 or C2 punctured the lookback swing low before turning up.
    """
    if len(candles) < lookback + 3:
        return None
    
    # Reference window: excludes the active 3-candle execution pattern [C0, C1, C2]
    ref_candles = candles[-(lookback + 3):-3]
    prior_bsl = max(c['high'] for c in ref_candles)
    prior_ssl = min(c['low'] for c in ref_candles)
    
    c1 = candles[-2]
    c2 = candles[-1]
    
    # Check Bearish BSL Sweep (Displacement down following high breach)
    peak_high = max(c1['high'], c2['high'])
    if peak_high > prior_bsl and c1['close'] < c1['open']:
        penetration = peak_high - prior_bsl
        return LiquiditySweep(
            pool_type="BSL",
            level=prior_bsl,
            sweep_candle_time=c1.get('time', 0),
            penetration_pts=penetration
        )
        
    # Check Bullish SSL Sweep (Displacement up following low breach)
    trough_low = min(c1['low'], c2['low'])
    if trough_low < prior_ssl and c1['close'] > c1['open']:
        penetration = prior_ssl - trough_low
        return LiquiditySweep(
            pool_type="SSL",
            level=prior_ssl,
            sweep_candle_time=c1.get('time', 0),
            penetration_pts=penetration
        )
        
    return None

def evaluate_silver_bullet(
    symbol: str, 
    candles: List[Dict], 
    spread_pts: float = 0.0, 
    min_rr: float = MIN_RR_RATIO,
    enforce_sweep: bool = True
) -> Optional[SilverBulletSetup]:
    """
    Precision ICT Silver Bullet evaluation pipeline:
    Killzone -> Liquidity Sweep -> Displacement Body >= 70% -> FVG >= 0.3 ATR -> 50% MT
    """
    in_kz, kz_name = check_killzone()
    if not in_kz:
        return None
        
    # Guard: Require external liquidity sweep
    sweep = detect_liquidity_sweep(candles)
    if enforce_sweep and sweep is None:
        return None
        
    atr_val = calculate_atr(candles, period=14)
    fvg = find_active_fvg(candles, atr_val=atr_val)
    if not fvg:
        return None
        
    # Ensure direction aligns with the swept pool
    if sweep:
        if sweep.pool_type == "BSL" and fvg.direction != "BEARISH":
            return None  # Swept buy-side liquidity, must deliver bearish displacement
        if sweep.pool_type == "SSL" and fvg.direction != "BULLISH":
            return None  # Swept sell-side liquidity, must deliver bullish displacement
            
    recent_c1 = candles[-2]
    _, ratio, _ = detect_displacement(recent_c1['open'], recent_c1['high'], recent_c1['low'], recent_c1['close'])
    spread_buffer = spread_pts * SPREAD_BUFFER_MULT
    
    if fvg.direction == "BULLISH":
        entry = fvg.mean_threshold
        sl = (recent_c1['low'] - spread_buffer)
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + (risk * min_rr)
        return SilverBulletSetup(
            symbol=symbol,
            direction="BUY",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_reward=min_rr,
            killzone=kz_name,
            displacement_ratio=ratio,
            fvg=fvg,
            sweep=sweep
        )
        
    elif fvg.direction == "BEARISH":
        entry = fvg.mean_threshold
        sl = (recent_c1['high'] + spread_buffer)
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - (risk * min_rr)
        return SilverBulletSetup(
            symbol=symbol,
            direction="SELL",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_reward=min_rr,
            killzone=kz_name,
            displacement_ratio=ratio,
            fvg=fvg,
            sweep=sweep
        )

if __name__ == "__main__":
    print("[+] Compiling and validating Liquidity Sweep Engine...")
    kz_act, kz_name = check_killzone()
    print(f"[*] Killzone status: Active={kz_act} ({kz_name})")
    
    # Construct synthetic 25-bar fixture demonstrating an SSL Purge into Bullish Displacement
    fixture = [{"open": 105.0, "high": 106.0, "low": 104.0, "close": 104.5, "time": i} for i in range(22)]
    # Anchor SSL at 104.0
    fixture[-3] = {"open": 104.5, "high": 105.0, "low": 104.2, "close": 104.4, "time": 22} # C0
    # C1 wicks down to 103.2 (purging 104.0 SSL), then explodes to 114.0 (displacement)
    fixture[-2] = {"open": 104.4, "high": 114.5, "low": 103.2, "close": 114.0, "time": 23} # C1 (Purge + MSS)
    # C2 confirms gap (Low: 106.5 > High of C0: 105.0)
    fixture[-1] = {"open": 114.0, "high": 115.0, "low": 106.5, "close": 113.0, "time": 24} # C2 (Bullish FVG)
    
    sweep = detect_liquidity_sweep(fixture)
    if sweep:
        print(f"[+] Verified Sweep: Pool={sweep.pool_type} | Level={sweep.level:.2f} | Penetration={sweep.penetration_pts:.2f}")
    else:
        print("[-] Sweep detection failed.")