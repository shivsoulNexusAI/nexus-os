import datetime
import re

with open('mss_matrix.py', 'r', encoding='utf-8') as f:
    text = f.read()

killzone_engine = '''
# ==============================================================================
# ICT KILLZONE SESSION FILTER (INSTITUTIONAL LIQUIDITY WINDOWS)
# ==============================================================================

def audit_ict_killzone(symbol: str = "") -> dict:
    """
    Evaluates whether the current UTC time falls within an active ICT institutional Killzone:
    - London Open Killzone  : 07:00 - 10:00 UTC
    - New York Open Killzone: 12:00 - 15:00 UTC
    - London Close Killzone : 15:00 - 17:00 UTC
    All other hours are classified as CHOP / OFF_SESSION.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cur_hour = now_utc.hour + (now_utc.minute / 60.0)

    # 1. London Open Killzone (07:00 - 10:00 UTC)
    if 7.0 <= cur_hour < 10.0:
        return {"in_killzone": True, "session": "LONDON_OPEN", "time_utc": now_utc.strftime("%H:%M UTC")}

    # 2. New York Open Killzone (12:00 - 15:00 UTC)
    elif 12.0 <= cur_hour < 15.0:
        return {"in_killzone": True, "session": "NEW_YORK_OPEN", "time_utc": now_utc.strftime("%H:%M UTC")}

    # 3. London Close Killzone (15:00 - 17:00 UTC)
    elif 15.0 <= cur_hour < 17.0:
        return {"in_killzone": True, "session": "LONDON_CLOSE", "time_utc": now_utc.strftime("%H:%M UTC")}

    # Off-Session (Asian Range / Dead Zones)
    else:
        return {
            "in_killzone": False,
            "session": "OFF_SESSION_CHOP",
            "time_utc": now_utc.strftime("%H:%M UTC"),
            "reason": f"Off-Session ({now_utc.strftime('%H:%M UTC')}): Outside London/NY Killzones"
        }
'''

if 'def audit_ict_killzone' not in text:
    text = killzone_engine.strip() + '\n\n' + text

# Wire Killzone validation into run_red_team_validation
if 'audit_ict_killzone' not in text or 'Killzone Veto' not in text:
    # Inject Killzone check at the top of run_red_team_validation
    target = 'def run_red_team_validation('
    replacement = '''def run_red_team_validation(
    # Gate 0: ICT Killzone Filter (Strictly block off-session chop)
    kz = audit_ict_killzone(symbol)
    if not kz["in_killzone"] and "BTC" not in symbol:
        return True, f"Killzone Veto: {kz['reason']}"
'''
    text = text.replace(target, replacement, 1)

with open('mss_matrix.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('[+] Successfully integrated ICT Killzone Filter into mss_matrix.py.')
