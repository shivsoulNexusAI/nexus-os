import MetaTrader5 as mt5
from apex_ml_feature_engine import ApexMicrostructureML

PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
LOGIN = 278029146
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"

if not mt5.initialize(path=PATH, login=LOGIN, password=PASSWORD, server=SERVER, portable=True):
    print(f"MT5 Init Failed: {mt5.last_error()}")
    quit()

print("=" * 70)
print(f"APEX MICROSTRUCTURE ML FEATURE AUDIT (ACCOUNT: {LOGIN})")
print("=" * 70)

symbols = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "USDJPY"]
for sym in symbols:
    res = ApexMicrostructureML.extract_features(sym)
    if res is None:
        print(f"{sym:<7} | OFFLINE (No rates/ticks)")
        continue
    
    bias = res["bias"]
    prob = res["probability"] * 100.0
    ofi = res["ofi"]
    sp_ratio = res["spread_ratio"]
    print(f"{sym:<7} | Bias: {bias:^15} | P(Win): {prob:5.1f}% | OFI: {ofi:>+5.2f} | SpreadRatio: {sp_ratio:4.2f}")

mt5.shutdown()
