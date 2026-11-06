path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

idx_target = -1
for i in range(2000, min(len(lines), 2040)):
    if "target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID" in lines[i]:
        idx_target = i
        break

if idx_target != -1:
    print(f"[*] Found target_id assignment at line {idx_target + 1}")
    dash_idx = -1
    for j in range(idx_target, min(len(lines), idx_target + 10)):
        if "if DASHBOARD_MSG_ID:" in lines[j]:
            dash_idx = j
            break

    end_idx = -1
    if dash_idx != -1:
        for k in range(dash_idx, min(len(lines), dash_idx + 35)):
            if "send_message" in lines[k]:
                for t in range(k, min(len(lines), k + 10)):
                    if "except" in lines[t]:
                        end_idx = t + 2
                        break
                break

    if dash_idx != -1 and end_idx != -1:
        indent = " " * (len(lines[dash_idx]) - len(lines[dash_idx].lstrip()))
        replacement = [
            f"{indent}if not board_text or not str(board_text).strip():\n",
            f"{indent}    continue\n",
            f"{indent}\n",
            f"{indent}if DASHBOARD_MSG_ID:\n",
            f"{indent}    try:\n",
            f"{indent}        await app.bot.edit_message_text(chat_id=target_id, message_id=DASHBOARD_MSG_ID, text=board_text, reply_markup=markup)\n",
            f"{indent}    except Exception:\n",
            f"{indent}        pass\n",
            f"{indent}else:\n",
            f"{indent}    try:\n",
            f"{indent}        msg = await app.bot.send_message(chat_id=target_id, text=board_text, reply_markup=markup)\n",
            f"{indent}        DASHBOARD_MSG_ID = msg.message_id\n",
            f"{indent}    except Exception as dbe:\n",
            f"{indent}        print(f'[!] Dashboard broadcast error: {{dbe}}')\n"
        ]
        lines = lines[:dash_idx] + replacement + lines[end_idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("[+] Replaced broadcast block with universal guard and message_id tracker.")
    else:
        print(f"[-] Markers missing: dash_idx={dash_idx}, end_idx={end_idx}")
else:
    print("[-] target_id anchor not found.")
