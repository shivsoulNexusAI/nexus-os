import datetime
import MetaTrader5 as mt5

def compute_today_ledger_stats():
    try:
        now = datetime.datetime.now()
        midnight_ts = datetime.datetime(now.year, now.month, now.day, 0, 0, 0).timestamp()
        deals = mt5.history_deals_get(midnight_ts, now.timestamp()) or []
        closed = [d for d in deals if d.entry == 1 and abs(d.profit) > 0.0001]
        tot_profit = sum(d.profit for d in closed)
        wins = len([d for d in closed if d.profit > 0])
        losses = len([d for d in closed if d.profit < 0])
        tot = len(closed)
        wr = (wins / tot * 100) if tot > 0 else 0.0
        return tot_profit, wins, losses, tot, wr
    except Exception:
        return 0.0, 0, 0, 0, 0.0

with open('telegram_interactive.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Inject compute_today_ledger_stats if not present
if 'def compute_today_ledger_stats' not in text:
    func_code = '''
def compute_today_ledger_stats():
    try:
        now = datetime.datetime.now()
        midnight_ts = datetime.datetime(now.year, now.month, now.day, 0, 0, 0).timestamp()
        deals = mt5.history_deals_get(midnight_ts, now.timestamp()) or []
        closed = [d for d in deals if d.entry == 1 and abs(d.profit) > 0.0001]
        tot_profit = sum(d.profit for d in closed)
        wins = len([d for d in closed if d.profit > 0])
        losses = len([d for d in closed if d.profit < 0])
        tot = len(closed)
        wr = (wins / tot * 100) if tot > 0 else 0.0
        return tot_profit, wins, losses, tot, wr
    except Exception:
        return 0.0, 0, 0, 0, 0.0
'''
    text = func_code.strip() + '\n\n' + text

# 2. Inject ledger stats into the dashboard card string
if "TODAY'S LEDGER" not in text:
    target = '📡 <b>ICT MULTI-ASSET RADAR:</b>'
    replacement = (
        '📊 <b>TODAY\'S LEDGER:</b> <code>${tot_prof:+,.2f}</code> | '
        '<b>WR:</b> <code>{wr:.1f}%</code> ({wins}W / {losses}L)\\n\\n'
        '📡 <b>ICT MULTI-ASSET RADAR:</b>'
    )
    if target in text:
        text = text.replace(target, replacement, 1)
        # Ensure variables are computed right before the card is formatted
        calc_stmt = 'tot_prof, wins, losses, tot_deals, wr = compute_today_ledger_stats()'
        if 'acc = mt5.account_info()' in text and calc_stmt not in text:
            text = text.replace('acc = mt5.account_info()', 'acc = mt5.account_info()\n    ' + calc_stmt)

with open('telegram_interactive.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('[+] Successfully injected realized PnL and win/loss tally into telegram_interactive.py.')
