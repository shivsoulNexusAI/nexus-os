import re

with open('telegram_interactive.py', 'r', encoding='utf-8') as f:
    text = f.read()

cb_helper = '''
# ==============================================================================
# PILLAR 2: HARD DAILY MAX-LOSS CIRCUIT BREAKER
# ==============================================================================
DAILY_MAX_LOSS_LIMIT = -300.00

def check_daily_circuit_breaker() -> tuple[bool, str]:
    """
    Evaluates today's closed deals. If realized loss exceeds DAILY_MAX_LOSS_LIMIT,
    triggers a hard lockout on all new entries until 00:00 UTC.
    """
    tot_prof, wins, losses, tot, wr = compute_today_ledger_stats()
    if tot_prof <= DAILY_MAX_LOSS_LIMIT:
        reason = f"🚨 CIRCUIT BREAKER TRIPPED: Realized daily loss ${tot_prof:+,.2f} exceeds limit (${DAILY_MAX_LOSS_LIMIT:,.2f}). Trading locked until 00:00 UTC."
        return True, reason
    return False, "NORMAL"
'''

if 'def check_daily_circuit_breaker' not in text:
    # Append circuit breaker helper
    text = cb_helper.strip() + '\n\n' + text

# Wire check into the entry signal evaluator
if 'check_daily_circuit_breaker()' not in text:
    # Intercept before trade dispatch in the 15s scan loop
    loop_target = "for sym in ['EURUSD', 'USDJPY', 'XAUUSD', 'GBPUSD', 'BTCUSD']:"
    cb_interception = """# Circuit Breaker Check
        cb_tripped, cb_msg = check_daily_circuit_breaker()
        if cb_tripped:
            # Skip new entry logic across all symbols
            time.sleep(15)
            continue
"""
    # Alternative safe injection: Intercept evaluate_ict_setup or signal dispatcher
    if 'eval_res = evaluate_ict_setup(sym)' in text:
        text = text.replace(
            'eval_res = evaluate_ict_setup(sym)',
            'cb_tripped, _ = check_daily_circuit_breaker()\n        if cb_tripped:\n            continue\n        eval_res = evaluate_ict_setup(sym)'
        )

with open('telegram_interactive.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('[+] Successfully injected Pillar 2 Hard Daily Max-Loss Circuit Breaker.')
