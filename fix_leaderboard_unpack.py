import re

path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# 1. Clean up duplicate `_raw` checking blocks between 1955 and 1985
clean_lines = []
for idx, line in enumerate(lines):
    if 1956 <= idx <= 1982:
        if "if isinstance(_raw, (tuple, list)):" in line and any("if isinstance(_raw" in l for l in clean_lines[-6:]):
            continue
        if any(token in line for token in ["ok = bool(_raw[0])", "res_msg = str(_raw[1])", "ticket = _raw[2]", "ok, res_msg, ticket = False"]):
            if any(token in l for l in clean_lines[-6:] for token in ["ok = bool(_raw[0])", "ok, res_msg, ticket = False"]):
                continue
    clean_lines.append(line)

lines = clean_lines

# 2. Defensively wrap line 2035: board_text, markup = render_leaderboard_card(...)
for idx, line in enumerate(lines):
    if "render_leaderboard_card" in line and "=" in line and "def " not in line:
        indent = " " * (len(line) - len(line.lstrip()))
        print(f"[*] Patching render_leaderboard_card unpack at line {idx+1}")
        lines[idx] = (
            f"{indent}_card_res = render_leaderboard_card(scans, autopilot_status=autopilot_status)\n"
            f"{indent}if isinstance(_card_res, (tuple, list)) and len(_card_res) >= 2:\n"
            f"{indent}    board_text, markup = _card_res[0], _card_res[1]\n"
            f"{indent}elif isinstance(_card_res, (tuple, list)) and len(_card_res) == 1:\n"
            f"{indent}    board_text, markup = _card_res[0], None\n"
            f"{indent}else:\n"
            f"{indent}    board_text, markup = str(_card_res or ''), None\n"
        )
        break

# 3. Patch bare returns inside def render_leaderboard_card
in_func = False
func_indent = 0
for idx, line in enumerate(lines):
    if "def render_leaderboard_card(" in line:
        in_func = True
        func_indent = len(line) - len(line.lstrip())
        print(f"[*] Found render_leaderboard_card at line {idx+1}")
        continue
    if in_func:
        if line.strip() and not line.startswith(" " * (func_indent + 1)):
            in_func = False
            continue
        stripped = line.strip()
        cur_indent = " " * (len(line) - len(line.lstrip()))
        if stripped in ("return", "return None"):
            lines[idx] = f'{cur_indent}return "", None\n'
            print(f"    Fixed bare return inside function at line {idx+1}")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Successfully patched render_leaderboard_card and its call site.")
