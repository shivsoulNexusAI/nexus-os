import MetaTrader5 as mt5
from mss_matrix import evaluate_ict_setup

if mt5.initialize():
    symbols = ['USDJPY', 'BTCUSD', 'EURUSD', 'XAUUSD', 'GBPUSD']
    header = "{:<8} | {:<18} | {:<8} | {:<18} | {:<7} | {}".format("SYMBOL", "H4 BIAS", "ZONE", "SWEEP", "VETOED", "REASON")
    print(header)
    print("-" * 95)
    for s in symbols:
        r = evaluate_ict_setup(s)
        row = "{:<8} | {:<18} | {:<8} | {:<18} | {:<7} | {}".format(
            s, r.get('h4_bias', 'N/A'), r.get('zone', 'N/A'), str(r.get('sweep', 'NONE')), str(r.get('vetoed', False)), r.get('veto_reason', 'N/A')
        )
        print(row)
    mt5.shutdown()
else:
    print("[-] MT5 failed to initialize.")
