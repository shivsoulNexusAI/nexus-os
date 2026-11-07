import os
import re
import json
import urllib.request

search_dirs = [
    r"C:\Quant-Straddle-Prod",
    r"C:\Quant-Nexus-Eng",
    r"C:\Quant-Nexus-Prod"
]
token_pattern = re.compile(r'(\d{8,10}:[A-Za-z0-9_-]{35})')

found_tokens = {}
for root_dir in search_dirs:
    if not os.path.exists(root_dir):
        continue
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            if f.endswith(('.json', '.env', '.py', '.txt', '.ini')):
                try:
                    with open(os.path.join(dirpath, f), 'r', encoding='utf-8-sig', errors='ignore') as fh:
                        for tok in token_pattern.findall(fh.read()):
                            found_tokens[tok.strip()[-3:].lower()] = tok.strip()
                except:
                    pass

chat_id = "5279761713"
lab_cfg_path = r"C:\Quant-Straddle-Prod\sandbox_gold_lab\lab_config.json"
if os.path.exists(lab_cfg_path):
    try:
        with open(lab_cfg_path, 'r', encoding='utf-8-sig') as f:
            c = json.load(f)
            chat_id = str(c.get("chat_id", chat_id))
    except:
        pass

t_5xu = found_tokens.get("5xu")
t_6yw = found_tokens.get("6yw")
t_ggg = next((v for k, v in found_tokens.items() if k.endswith("g") or "ggg" in k), None)

config = {
    "chat_id": chat_id,
    "nexus_ai_bot": {
        "name": "Nexus AI Bot",
        "token": t_5xu,
        "chat_id": chat_id,
        "role": "Autonomous Straddle Telemetry & High-Speed Execution"
    },
    "quant_alert_bot": {
        "name": "Quant Alert Bot",
        "token": t_6yw,
        "chat_id": chat_id,
        "role": "Macro Portfolio Governance, Account Delta & Risk Harvester"
    },
    "telegram_dev_guard_bot": {
        "name": "Dev Guard / Test Bot",
        "token": t_ggg,
        "chat_id": chat_id,
        "role": "Heartbeat Sentinel, 25MB RAM Watchdog & Host Telemetry"
    }
}

out_cfg_path = r"C:\Quant-Nexus-Eng\master_telegram_trio.json"
with open(out_cfg_path, 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2)

print(f"[+] Saved master config: {out_cfg_path}")

missions = [
    ("nexus_ai_bot", "⚡ <b>MISSION 1: NEXUS AI BOT ONLINE</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n• <b>Token Ref:</b> <code>...5XU</code>\n• <b>Role:</b> <code>HFT Straddle & Trailing Guard</code>\n• <b>Status:</b> <code>ARMED & ACTIVE</code>"),
    ("quant_alert_bot", "📊 <b>MISSION 2: QUANT ALERT BOT ONLINE</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n• <b>Token Ref:</b> <code>...6YW</code>\n• <b>Role:</b> <code>Portfolio Alpha & Governance</code>\n• <b>Status:</b> <code>SYNCHRONIZED</code>"),
    ("telegram_dev_guard_bot", "🛡️ <b>MISSION 3: DEV GUARD / TEST BOT ONLINE</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n• <b>Token Ref:</b> <code>...QGGg</code>\n• <b>Role:</b> <code>Host Watchdog & RAM Sentinel</code>\n• <b>Status:</b> <code>OPTIMAL</code>")
]

print("\n=== FIRING VERIFICATION HANDSHAKES ===")
for key, msg in missions:
    bot = config.get(key)
    if not bot or not bot.get("token"):
        print(f"[-] {key}: Missing token.")
        continue
    
    token = bot["token"]
    tgt_chat = bot["chat_id"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": tgt_chat, "text": msg, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode())
            if res.get("ok"):
                print(f"[+] {bot['name']} (ending ...{token[-4:]}) -> DISPATCH SUCCESSFUL")
            else:
                print(f"[-] {bot['name']} -> Error: {res}")
    except Exception as e:
        print(f"[-] {bot['name']} -> Request failed: {e}")