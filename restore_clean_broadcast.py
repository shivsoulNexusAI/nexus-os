path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Locate target_id
target_idx = -1
for i in range(2010, min(len(lines), 2040)):
    if "target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID" in lines[i]:
        target_idx = i
        break

if target_idx == -1:
    print("[-] target_id anchor not found.")
else:
    print(f"[*] Found target_id at line {target_idx + 1}")
    
    # Locate the daemon catch block (except asyncio.CancelledError or except Exception)
    end_idx = -1
    for j in range(target_idx, min(len(lines), target_idx + 60)):
        if "except asyncio.CancelledError:" in lines[j] or "except Exception as e:" in lines[j]:
            end_idx = j
            break

    if end_idx != -1:
        indent = " " * (len(lines[target_idx]) - len(lines[target_idx].lstrip()))
        clean_block = [
            lines[target_idx],
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
            f"{indent}await asyncio.sleep(15)\n",
            f"\n"
        ]
        lines = lines[:target_idx] + clean_block + lines[end_idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("[+] Replaced broadcast block with clean, syntax-aligned structure.")
    else:
        print("[-] Daemon exception anchor not found.")
