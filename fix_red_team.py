import re

with open('mss_matrix.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix broken run_red_team_validation signature if mangled
pattern = r'def run_red_team_validation\([\s\S]*?(?=def |class |\Z)'

clean_red_team = '''def run_red_team_validation(symbol: str, signal: str, entry: float, sl: float, htf_data: dict = None) -> tuple[bool, str]:
    """
    Sovereign Apex Red-Team Veto Gate:
    1. ICT Killzone Session Gate (Blocks off-session churn on FX/Metals)
    2. Macro Economic Sentinel (Blocks USD high-impact release windows)
    3. Structural Spread & Wick Validation
    """
    # Gate 0: ICT Killzone Filter (Exempt 24/7 crypto like BTC)
    kz = audit_ict_killzone(symbol)
    if not kz.get("in_killzone", False) and "BTC" not in symbol:
        return True, f"Killzone Veto: {kz.get('reason', 'Off-Session')}"

    # Gate 1: Macro News Sentinel Freeze
    try:
        from macro_sentinel import fetch_macro_freeze_status
        frozen, news_reason = fetch_macro_freeze_status(30)
        if frozen:
            return True, f"Macro News Freeze: {news_reason}"
    except Exception:
        pass

    # Gate 2: Structural Spread vs Risk Gate
    try:
        tick = mt5.symbol_info_tick(symbol)
        sym_info = mt5.symbol_info(symbol)
        if tick and sym_info:
            spread = (tick.ask - tick.bid)
            risk = abs(entry - sl)
            if risk > 0 and (spread / risk) > 0.20:
                return True, f"Spread Friction Veto: Spread is >20% of risk distance"
    except Exception:
        pass

    return False, "APPROVED"
'''

# Replace the run_red_team_validation definition cleanly
if 'def run_red_team_validation' in text:
    text = re.sub(r'def run_red_team_validation\([\s\S]*?(?=\ndef [a-zA-Z_]|\n# [=]+|\Z)', clean_red_team.strip() + '\n\n', text, count=1)

with open('mss_matrix.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('[+] Repaired run_red_team_validation and properly wired ICT Killzone Gate.')
