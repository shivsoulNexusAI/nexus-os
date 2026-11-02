path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

t_idx = -1
for i in range(2000, min(len(lines), 2040)):
    if "target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID" in lines[i]:
        t_idx = i
        break

if t_idx == -1:
    print("[-] target_id anchor not found.")
else:
    print(f"[*] Found target_id anchor at line {t_idx + 1}")
    indent = " " * (len(lines[t_idx]) - len(lines[t_idx].lstrip()))
    
    # Scan forward to locate the end of the malformed block (either a sleep or outer loop code)
    end_idx = -1
    for j in range(t_idx + 1, min(len(lines), t_idx + 45)):
        s = lines[j].strip()
        if "asyncio.sleep(" in s or "check_and_execute_daily_rollover" in s or "except " in s:
            end_idx = j
            if "asyncio.sleep(" in s:
                end_idx = j + 1
            break
            
    if end_idx == -1:
        end_idx = t_idx + 25

    clean_broadcast = [
        f"{lines[t_idx]}",
        f"{indent}if board_text and str(board_text).strip():\n",
        f"{indent}    if DASHBOARD_MSG_ID:\n",
        f"{indent}        try:\n",
        f"{indent}            await app.bot.edit_message_text(chat_id=target_id, message_id=DASHBOARD_MSG_ID, text=board_text, reply_markup=markup)\n",
        f"{indent}        except Exception:\n",
        f"{indent}            pass\n",
        f"{indent}    else:\n",
        f"{indent}        try:\n",
        f"{indent}            msg = await app.bot.send_message(chat_id=target_id, text=board_text, reply_markup=markup)\n",
        f"{indent}            DASHBOARD_MSG_ID = msg.message_id\n",
        f"{indent}        except Exception as dbe:\n",
        f"{indent}            print(f'[!] Dashboard broadcast error: {{dbe}}')\n",
        f"\n",
        f"{indent}await asyncio.sleep(15)\n"
    ]

    lines = lines[:t_idx] + clean_broadcast + lines[end_idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[+] Broadcast block successfully rebuilt between lines {t_idx + 1} and {end_idx + 1}.")
