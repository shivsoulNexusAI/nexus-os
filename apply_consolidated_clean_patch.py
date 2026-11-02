import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

# 1. Guard execute_market_order unpack
exec_pattern = r'(_raw\s*=\s*(?:await\s+asyncio\.to_thread\(execute_market_order[^\)]+\)|execute_market_order[^\n]+))(\s*\n)(\s*)(?:ok,\s*res_msg,\s*ticket\s*=.*)'
def replace_exec(m):
    prefix = m.group(1)
    nl = m.group(2)
    indent = m.group(3)
    return (
        f"{prefix}{nl}"
        f"{indent}if isinstance(_raw, (tuple, list)):\n"
        f"{indent}    ok = bool(_raw[0]) if len(_raw) > 0 else False\n"
        f"{indent}    res_msg = str(_raw[1]) if len(_raw) > 1 else ''\n"
        f"{indent}    ticket = _raw[2] if len(_raw) > 2 else None\n"
        f"{indent}else:\n"
        f"{indent}    ok, res_msg, ticket = False, str(_raw or ''), None"
    )
content = re.sub(exec_pattern, replace_exec, content, count=1)

# 2. Guard render_leaderboard_card unpack
card_pattern = r'(\s*)(board_text,\s*markup\s*=\s*render_leaderboard_card\([^\)]+\))'
def replace_card(m):
    indent = m.group(1)
    call_line = m.group(2)
    call_expr = call_line.split("=", 1)[1].strip()
    return (
        f"{indent}_card_res = {call_expr}\n"
        f"{indent}if isinstance(_card_res, (tuple, list)) and len(_card_res) >= 2:\n"
        f"{indent}    board_text, markup = _card_res[0], _card_res[1]\n"
        f"{indent}elif isinstance(_card_res, (tuple, list)) and len(_card_res) == 1:\n"
        f"{indent}    board_text, markup = _card_res[0], None\n"
        f"{indent}else:\n"
        f"{indent}    board_text, markup = str(_card_res or ''), None"
    )
content = re.sub(card_pattern, replace_card, content, count=1)

# 3. Guard broadcast block against empty text without skipping sleep
# Locate DASHBOARD_MSG_ID check and wrap edit/send safely
content = re.sub(
    r'(if\s+DASHBOARD_MSG_ID:)',
    r'if board_text and str(board_text).strip():\n                    \1',
    content,
    count=1
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("[+] Consolidated stabilization patch applied cleanly.")
