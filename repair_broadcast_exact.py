path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Locate target_id
t_idx = -1
for i in range(2010, min(len(lines), 2035)):
    if "target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID" in lines[i]:
        t_idx = i
        break

if t_idx == -1:
    print("[-] target_id anchor not found.")
else:
    print(f"[*] Found target_id at line {t_idx + 1}")
    
    # Locate where the next independent statement or outer block starts
    # We find any line after t_idx+2 that is indented with <= 16 spaces (excluding empty lines)
    end_idx = -1
    for j in range(t_idx + 2, min(len(lines), t_idx + 40)):
        line_str = lines[j]
        stripped = line_str.strip()
        if not stripped:
            continue
        indent = len(line_str) - len(line_str.lstrip())
        # If it's a new statement at 16 spaces that isn't part of the broken broadcast
        if indent <= 16 and not any(k in stripped for k in ["if DASHBOARD_MSG_ID", "if board_text", "else:", "try:", "except"]):
            end_idx = j
            break
        # Or if it hits an except block of the daemon
        if stripped.startswith("except"):
            end_idx = j
            break

    if end_idx == -1:
        # Fallback: span 20 lines from t_idx
        end_idx = t_idx + 20

    print(f"[*] Splicing out broken block from line {t_idx + 1} to {end_idx + 1}")
    print(f"[*] Next statement at line {end_idx + 1}: {lines[end_idx].strip()[:50]}")

    clean_block = [
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

    lines = lines[:t_idx] + clean_block + lines[end_idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("[+] Replaced broadcast block with clean 16-space indentation.")
