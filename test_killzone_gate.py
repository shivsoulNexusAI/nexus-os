import MetaTrader5 as mt5
from mss_matrix import audit_ict_killzone, evaluate_ict_setup

kz = audit_ict_killzone()
print("=" * 70)
print(f"🕒 TIME: {kz['time_utc']} | SESSION: {kz['session']} | IN KILLZONE: {kz['in_killzone']}")
print("=" * 70)

if mt5.initialize():
    for s in ['EURUSD', 'XAUUSD', 'GBPUSD', 'USDJPY', 'BTCUSD']:
        res = evaluate_ict_setup(s)
        status = "ALLOWED" if res.get('valid') else f"VETOED ({res.get('veto_reason')})"
        sig = str(res.get('signal'))
        print(f"{s:<8} | Signal: {sig:<5} | Status: {status}")
    mt5.shutdown()
else:
    print("[-] MT5 failed to initialize.")
