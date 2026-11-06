path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# 1. Locate target_id
t_idx = -1
for i in range(2010, min(len(lines), 2035)):
    if "target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID" in lines[i]:
        t_idx = i
        break

if t_idx == -1:
    print("[-] target_id anchor not found.")
else:
    print(f"[*] Found target_id at line {t_idx + 1}")

    # 2. Find the true outer boundary (either LAST_ROLLOVER_DATE, check_and_execute_daily_rollover, or except asyncio.CancelledError / except Exception as e:)
    end_idx = -1
    for j in range(t_idx + 1, min(len(lines), t_idx + 70)):
        s = lines[j].strip()
        # Look for outer daemon components
        if "check_and_execute_daily_rollover" in s or "LAST_ROLLOVER_DATE" in s:
            end_idx = j
            break
        if s.startswith("except asyncio.CancelledError:") or s.startswith("except Exception as e:"):
            end_idx = j
            break

    if end_idx != -1:
        print(f"[*] Found outer boundary at line {end_idx + 1}: {lines[end_idx].strip()[:50]}")
        
        # Replacement block with exact 16-space indentation
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
        
        lines = lines[:t_idx] + clean_section + lines[end_idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("[+] Replaced broadcast block successfully with exact 16-space indentation.")
    else:
        print("[-] Could not find genuine outer boundary.")
