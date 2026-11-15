import MetaTrader5 as mt5
from sniper_execution_router import route_silver_bullet_order

APEX_TERMINAL = r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe"
if mt5.initialize(path=APEX_TERMINAL, portable=False, timeout=10000):
    acc = mt5.account_info()
    print("=" * 85)
    print(f"TESTING DIRECT ORDER ROUTING VALIDATION ON #{acc.login}")
    print(f"Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Margin Free: ${acc.margin_free:,.2f}")
    
    # Construct a synthetic mock setup to evaluate guards
    class MockSweep:
        pool_type = "SSL"
        level = 1.1150
        
    class MockSetup:
        symbol = "EURUSD"
        direction = "BUY"
        killzone = "LONDON_OPEN"
        entry_price = mt5.symbol_info_tick("EURUSD").ask
        stop_loss = entry_price - 0.0015
        take_profit = entry_price + 0.0030
        sweep = MockSweep()

    setup = MockSetup()
    print(f"Evaluating dry-run institutional guards for {setup.symbol} {setup.direction} @ {setup.entry_price:.5f}...")
    ok, msg, details = route_silver_bullet_order(setup, dry_run=True)
    print(f"Router Result -> Allowed: {ok} | Reason/Status: {msg} | Details: {details}")
    mt5.shutdown()
    print("=" * 85)
else:
    print(f"[-] Terminal init failed: {mt5.last_error()}")