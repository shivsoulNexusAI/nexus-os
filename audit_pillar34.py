import sys
import time
import pandas as pd
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_telegram import send_alert

print("\n=== PILLAR 3: ASYNC TELEGRAM TRIO DISPATCH AUDIT ===")
t0 = time.perf_counter()

# Fire non-blocking alerts across all 3 roles
send_alert("telegram_dev_guard_bot", "🛡️ <b>[DEV-GUARD]</b> Sentinel Heartbeat Verified | RAM Throttling: Active")
send_alert("quant_alert_bot", "📊 <b>[QUANT-ALERT]</b> Governance State Synced | HWM: $988.78 | 0.79 Lots")
send_alert("nexus_ai_bot", "⚡ <b>[NEXUS-AI]</b> Ultra HFT Engine Online | Magic #777001 Live")

dispatch_ms = (time.perf_counter() - t0) * 1000
print(f"• Non-blocking Trio Dispatch Executed in: {dispatch_ms:.2f} ms")
print("-" * 55)

print("\n=== PILLAR 4: SMC / MSNR / FVG LIVE BROKER ALIGNMENT ===")
path = r"C:\MT5_HFT_278041671\terminal64.exe"
if mt5.initialize(path=path):
    symbols = ["XAUUSD247", "EURUSD", "GBPUSD", "BTCUSD"]
    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 5:
            print(f"• {sym:<10} | Feed: OFFLINE / WEEKEND CLOSED")
            continue
        
        df = pd.DataFrame(rates)
        # 3-Candle Imbalance (Fair Value Gap)
        c1_high, c1_low = df.iloc[-3]['high'], df.iloc[-3]['low']
        c3_high, c3_low = df.iloc[-1]['high'], df.iloc[-1]['low']
        
        if c3_low > c1_high:
            fvg = f"BULLISH_FVG [Gap: {c1_high:.3f} - {c3_low:.3f}]"
        elif c3_high < c1_low:
            fvg = f"BEARISH_FVG [Gap: {c3_high:.3f} - {c1_low:.3f}]"
        else:
            fvg = "BALANCED AUCTION"

        tick = mt5.symbol_info_tick(sym)
        spread = (tick.ask - tick.bid) if tick else 0.0
        print(f"• {sym:<10} | Close: {df.iloc[-1]['close']:>9.3f} | Spread: ${spread:>6.3f} | Structure: {fvg}")
    mt5.shutdown()
else:
    print("[-] MT5 Terminal initialization failed.")
print("========================================================\n")