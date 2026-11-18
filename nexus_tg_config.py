# =====================================================================
# SHIVSOUL NEXUS v7.0 // JSON + ENV TELEGRAM CREDENTIAL LOADER
# =====================================================================
import os
import json
from pathlib import Path

TOKEN_KEYS = {"telegram_bot_token", "bot_token", "tg_token", "tg_bot_token", "token"}
CHAT_KEYS = {"telegram_chat_id", "chat_id", "tg_chat_id", "admin_chat_id"}


def _walk_json(obj, found: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if isinstance(v, (str, int)) and str(v).strip():
                val = str(v).strip()
                if kl in TOKEN_KEYS and ":" in val and "token" not in found:
                    found["token"] = val
                elif kl in CHAT_KEYS and "chat_id" not in found:
                    found["chat_id"] = val
            elif isinstance(v, (dict, list)):
                _walk_json(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json(item, found)


def resolve_telegram_credentials(base_dir: Path = Path(".")) -> tuple[str, str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        return token, chat_id, "environment"

    for json_file in sorted(base_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8-sig"))
            found: dict = {}
            _walk_json(data, found)
            if not token and found.get("token"):
                token = found["token"]
            if not chat_id and found.get("chat_id"):
                chat_id = found["chat_id"]
            if token and chat_id:
                return token, chat_id, json_file.name
        except Exception:
            continue

    return token, chat_id, "unresolved"
