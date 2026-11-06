import MetaTrader5 as mt5
from apex_omega_engine import ApexOmegaEngine

PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
LOGIN = 278029146
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"

if not mt5.initialize(path=PATH, login=LOGIN, password=PASSWORD, server=SERVER, portable=True):
    print(f"MT5 Init Failed: {mt5.last_error()}")
    quit()

print("=" * 85)
print("QUANT NEXUS OMEGA FX | MSS & LIQUIDITY NOISE PROBE")
print("=" * 85)

for sym in ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "USDJPY"]:
    r = ApexOmegaEngine.analyze_asset(sym)
    if r:
        bias = r["bias"]
        mss = str(r["mss"])
        prob = r["prob"] * 100.0
        sig = str(r["signal"])
        buff = r["buffer"]
        print(f"{sym:<7} | Bias: {bias:^14} | MSS: {mss:^5} | P(Win): {prob:5.1f}% | Signal: {sig:^4} | SL Cushion: {buff}")

mt5.shutdown()
