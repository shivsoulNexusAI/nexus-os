path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Locate target_id
t_idx = -1
for i in range(2015, min(len(lines), 2035)):
    if "target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID" in lines[i]:
        t_idx = i
        break

if t_idx == -1:
    print("[-] target_id anchor not found.")
else:
    print(f"[*] Found target_id anchor at line {t_idx + 1}")
    
    # Locate where the next daemon logic begins (LAST_ROLLOVER_DATE, check_and_execute, or except)
    next_idx = -1
    for j in range(t_idx + 1, min(len(lines), t_idx + 60)):
        s = lines[j].strip()
        if "check_and_execute_daily_rollover" in s or "LAST_ROLLOVER_DATE" in s or s.startswith("except "):
            next_idx = j
            break

    if next_idx == -1:
        # Fallback to scanning for the next unindented/outer block
        for j in range(t_idx + 1, min(len(lines), t_idx + 40)):
            if lines[j].strip().startswith("except"):
                next_idx = j
                break

    if next_idx != -1:
        print(f"[*] Found boundary anchor at line {next_idx + 1}: {lines[next_idx].strip()[:40]}")
        
        # Clean block using standard 16-space baseline for inside the scan loop
        clean_section = [
            "                target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID\n",
            "                if board_text and str(board_text).strip():\n",
            "                    if DASHBOARD_MSG_ID:\n",
            "                        try:\n",
            "                            await app.bot.edit_message_text(chat_id=target_id, message_id=DASHBOARD_MSG_ID, text=board_text, reply_markup=markup)\n",
            "                        except Exception:\n",
            "                            pass\n",
            "                    else:\n",
            "                        try:\n",
            "                            msg = await app.bot.send_message(chat_id=target_id, text=board_text, reply_markup=markup)\n",
            "                            DASHBOARD_MSG_ID = msg.message_id\n",
            "                        except Exception as dbe:\n",
            "                            print(f'[!] Dashboard broadcast error: {dbe}')\n",
            "\n",
            "                await asyncio.sleep(15)\n",
            "\n"
        ]
        
        lines = lines[:t_idx] + clean_section + lines[next_idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("[+] Replaced broadcast block with clean, verified indentation.")
    else:
        print("[-] Could not find clean boundary anchor.")
