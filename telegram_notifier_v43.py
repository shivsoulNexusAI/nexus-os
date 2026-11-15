import json
import threading
import urllib.request
from pathlib import Path

BASE_DIR = Path(r"C:\Quant-Nexus-Eng")

def _load_creds():
    # Priority 1: telegram_nexus_config.py / telegram_config.py
    for mod_name in ("telegram_nexus_config", "telegram_config", "telegram_gold_config"):
        cfg_file = BASE_DIR / f"{mod_name}.py"
        if cfg_file.exists():
            ns = {}
            try:
                exec(cfg_file.read_text(encoding="utf-8"), ns)
                token = ns.get("BOT_TOKEN") or ns.get("TELEGRAM_TOKEN") or ns.get("TOKEN")
                chat_id = ns.get("CHAT_ID") or ns.get("TELEGRAM_CHAT_ID") or ns.get("ADMIN_ID")
                if token and chat_id:
                    return str(token).strip(), str(chat_id).strip()
            except Exception:
                pass

    # Priority 2: JSON config files
    for json_name in ("master_telegram_trio.json", "t2_telegram_config.json", "telegram_config.json", "t1_telegram_config.json"):
        jf = BASE_DIR / json_name
        if jf.exists():
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Handle nested silo dicts or flat dicts
                    for candidate in [data] + [v for v in data.values() if isinstance(v, dict)]:
                        token = candidate.get("bot_token") or candidate.get("token") or candidate.get("BOT_TOKEN")
                        chat_id = candidate.get("chat_id") or candidate.get("CHAT_ID")
                        if token and chat_id:
                            return str(token).strip(), str(chat_id).strip()
            except Exception:
                pass
    return "", ""

def _post_sync(text: str):
    token, chat_id = _load_creds()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            resp.read()
    except Exception:
        pass

def send_v43_alert(text: str, sync: bool = False):
    if sync:
        _post_sync(text)
    else:
        threading.Thread(target=_post_sync, args=(text,), daemon=True).start()