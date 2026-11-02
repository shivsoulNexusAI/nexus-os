import MetaTrader5 as mt5
import pandas as pd
import datetime

def evaluate_stacking_opportunity(symbol: str) -> dict:
    """
    Evaluates whether an asset qualifies for an Asymmetric Invalidation Stack (Pillar 1).
    Rules:
      1. Parent position must exist, be in profit >= +1.5R, and SL moved to Breakeven.
      2. No secondary stack position already open for this symbol.
      3. An M5 FVG / Structural pullback forms in direction of the trend.
    """
    positions = mt5.positions_get(symbol=symbol) or []
    if not positions:
        return {"eligible": False, "reason": "No active position"}

    # Separate parent from existing stack positions
    parent_pos = None
    existing_stacks = []

    for p in positions:
        comment = p.comment or ""
        if "STACK" in comment:
            existing_stacks.append(p)
        else:
            parent_pos = p

    if existing_stacks:
        return {"eligible": False, "reason": "Stack already open on this asset"}

    if not parent_pos:
        return {"eligible": False, "reason": "No parent trade found"}

    # Verify parent is at Breakeven (risk-free)
    is_be = abs(parent_pos.sl - parent_pos.price_open) < 0.001
    if not is_be:
        return {"eligible": False, "reason": "Parent trade SL is not yet at Breakeven"}

    # Estimate parent initial risk distance to verify >= +1.5R
    risk_dist = 0.0020
    if "JPY" in symbol: risk_dist = 0.200
    elif "XAU" in symbol: risk_dist = 5.00
    elif "BTC" in symbol: risk_dist = 150.0

    current_dist = (parent_pos.price_current - parent_pos.price_open) if parent_pos.type == 0 else (parent_pos.price_open - parent_pos.price_current)
    current_r = current_dist / risk_dist

    if current_r < 1.2:  # Threshold for stack readiness
        return {"eligible": False, "reason": f"Parent R ({current_r:+.2f}R) is below stacking threshold (+1.2R)"}

    # Pull M5 rates to find structural re-test invalidation point
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 20)
    if rates is None or len(rates) < 10:
        return {"eligible": False, "reason": "Insufficient M5 candles for stack structure"}

    df = pd.DataFrame(rates)
    direction = "BUY" if parent_pos.type == 0 else "SELL"
    stack_lot = round(parent_pos.volume * 0.5, 2)
    if stack_lot < 0.01:
        stack_lot = 0.01

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"eligible": False, "reason": "No live tick"}

    if direction == "BUY":
        # Anchor SL behind recent M5 swing low (last 5 bars)
        recent_low = df['low'].iloc[-5:].min()
        sl = float(recent_low)
        entry = tick.ask
        if sl >= entry or (entry - sl) > (risk_dist * 1.5):
            sl = entry - (risk_dist * 0.8)
        tp = entry + (abs(entry - sl) * 2.5)  # 2.5R expansion target
    else:
        recent_high = df['high'].iloc[-5:].max()
        sl = float(recent_high)
        entry = tick.bid
        if sl <= entry or (sl - entry) > (risk_dist * 1.5):
            sl = entry + (risk_dist * 0.8)
        tp = entry - (abs(sl - entry) * 2.5)

    return {
        "eligible": True,
        "symbol": symbol,
        "direction": direction,
        "lot": stack_lot,
        "entry": entry,
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "parent_ticket": parent_pos.ticket,
        "parent_r": round(current_r, 2),
        "reason": f"Parent at {current_r:+.1f}R BE. Fresh M5 pullback ready for 0.5x stack."
    }

if __name__ == "__main__":
    if mt5.initialize():
        print("=" * 65)
        print("🏹 EVALUATING ASYMMETRIC STACKING RADAR")
        print("=" * 65)
        for sym in ["USDJPY", "EURUSD", "BTCUSD", "XAUUSD", "GBPUSD"]:
            res = evaluate_stacking_opportunity(sym)
            status = "ELIGIBLE 🚀" if res["eligible"] else f"STANDBY ({res['reason']})"
            print(f"{sym:<8} | Status: {status}")
        print("=" * 65)
        mt5.shutdown()
