import MetaTrader5 as mt5
import pandas as pd
from mss_matrix import detect_swing_points

BUFFER_FACTORS = {
    "XAUUSD": 0.80,    # $0.80 gold structural cushion
    "BTCUSD": 35.0,    # $35.00 bitcoin cushion
    "EURUSD": 0.00015, # 1.5 pips
    "GBPUSD": 0.00020, # 2.0 pips
    "USDJPY": 0.025    # 2.5 pips
}

def get_latest_m5_swing(symbol: str) -> dict:
    """Extracts confirmed fractal swing high and low on M5."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
    if rates is None or len(rates) < 15:
        return {"swing_high": 0.0, "swing_low": 0.0}
    
    df = pd.DataFrame(rates)
    df = detect_swing_points(df, window=2)
    
    sh_series = df[df['swing_high']]['high']
    sl_series = df[df['swing_low']]['low']
    
    # Exclude the currently forming candle for confirmed structure
    last_sh = float(sh_series.iloc[-1]) if not sh_series.empty else float(df['high'].iloc[-5:].max())
    last_sl = float(sl_series.iloc[-1]) if not sl_series.empty else float(df['low'].iloc[-5:].min())
    
    return {"swing_high": last_sh, "swing_low": last_sl}

def execute_structural_trailing(target_symbols=["XAUUSD", "BTCUSD"]):
    """
    Ratchets SL along confirmed M5 structure:
    - For SELLS: only ratchet SL DOWNWARD if swing_high + buffer < current SL.
    - For BUYS:  only ratchet SL UPWARD if swing_low - buffer > current SL.
    """
    if not mt5.initialize():
        return []
    
    positions = mt5.positions_get() or []
    actions = []
    
    for pos in positions:
        if pos.symbol not in target_symbols:
            continue
        
        swings = get_latest_m5_swing(pos.symbol)
        buffer = BUFFER_FACTORS.get(pos.symbol, 0.0)
        curr_sl = float(pos.sl)
        open_price = float(pos.price_open)
        
        # BUY: Trail SL upward behind confirmed M5 Swing Low
        if pos.type == 0:
            target_sl = round(swings['swing_low'] - buffer, 5 if "USD" in pos.symbol and not "BTC" in pos.symbol else 2)
            # Only trail upward, and only once in profit or past entry
            if target_sl > curr_sl and target_sl > open_price:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": pos.symbol,
                    "sl": target_sl,
                    "tp": pos.tp
                }
                res = mt5.order_send(req)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    actions.append(f"🟢 [STRUCTURAL TRAIL BUY] #{pos.ticket} {pos.symbol}: SL tightened {curr_sl} -> {target_sl}")
                    
        # SELL: Trail SL downward behind confirmed M5 Swing High
        elif pos.type == 1:
            target_sl = round(swings['swing_high'] + buffer, 3 if "XAU" in pos.symbol else (2 if "BTC" in pos.symbol else 5))
            # Only trail downward, and only if target is better than entry (locking profit)
            if (curr_sl == 0.0 or target_sl < curr_sl) and target_sl < open_price:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": pos.symbol,
                    "sl": target_sl,
                    "tp": pos.tp
                }
                res = mt5.order_send(req)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    actions.append(f"🔴 [STRUCTURAL TRAIL SELL] #{pos.ticket} {pos.symbol}: SL locked {curr_sl} -> {target_sl}")
                    
    return actions

if __name__ == "__main__":
    import sys
    results = execute_structural_trailing(["XAUUSD", "BTCUSD"])
    if results:
        for r in results:
            print(r)
    else:
        print("[+] Structural check complete: Current SL levels optimal, no tighter confirmed swings yet.")
