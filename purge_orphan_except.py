path = r"C:\Quant-Nexus-Eng\telegram_interactive.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

t_idx = -1
for i in range(2015, min(len(lines), 2035)):
    if "target_id = ACTIVE_CHAT_ID or ADMIN_CHAT_ID" in lines[i]:
        t_idx = i
        break

if t_idx == -1:
    print("[-] target_id not found")
    exit()

print(f"[*] target_id at line {t_idx + 1}")

# Scan forward past all the broadcast and leftover except/else lines until we hit real subsequent code
# We look for lines containing check_and_execute, LAST_ROLLOVER, or lines outside the while block
cutoff_idx = -1
for j in range(t_idx + 1, min(len(lines), t_idx + 50)):
    stripped = lines[j].strip()
    if any(k in stripped for k in ["check_and_execute_daily_rollover", "LAST_ROLLOVER_DATE", "check_daily_circuit_breaker"]):
        cutoff_idx = j
        break
    if stripped.startswith("except asyncio.CancelledError") or stripped.startswith("except Exception as e:"):
        cutoff_idx = j
        break

if cutoff_idx == -1:
    # If no rollover check, find where indentation drops below 16
    for j in range(t_idx + 15, min(len(lines), t_idx + 50)):
        if lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip())) < 16:
            cutoff_idx = j
            break

print(f"[*] Next legitimate code block at line {cutoff_idx + 1}: {lines[cutoff_idx].strip()[:50]}")

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

lines = lines[:t_idx] + clean_block + lines[cutoff_idx:]
with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("[+] Successfully excised orphan blocks and inserted clean broadcast logic.")
