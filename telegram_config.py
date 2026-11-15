import json
from pathlib import Path

_CONFIG_JSON = Path(r"C:\Quant-Nexus-Eng\telegram_tripartite_bots.json")

_DEFAULT_PAYLOAD = {
    "chat_id": 5279761713,
    "bots": {
        "T1": {
            "bot_name": "Quant Alert Bot (Terminal 1)",
            "token": "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw",
            "account": 278062038,
        },
        "T2": {
            "bot_name": "Nexus AI Bot (Terminal 2)",
            "token": "8578781048:AAHCDrhqtH6gwcm1R3YZvNIu9zvAPM5Y5xU",
            "account": 278062039,
        },
        "T3": {
            "bot_name": "Nexus Gold 24/7 (Terminal 3)",
            "token": "9288476562:AAEtFGf4kAfUS-tYmb6Lw-dulLEozwx_A5I",
            "account": 278062042,
        },
    },
}

def load_tripartite_telegram_config() -> dict:
    """Loads telegram_tripartite_bots.json as the primary canonical token source."""
    if _CONFIG_JSON.exists():
        try:
            return json.loads(_CONFIG_JSON.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return _DEFAULT_PAYLOAD

_CFG = load_tripartite_telegram_config()
_BOTS = _CFG.get("bots", _DEFAULT_PAYLOAD["bots"])

TELEGRAM_CHAT_ID = str(_CFG.get("chat_id", _DEFAULT_PAYLOAD["chat_id"]))
CHAT_ID = TELEGRAM_CHAT_ID

# Sleeve-specific bot tokens
T1_BOT_TOKEN = _BOTS.get("T1", {}).get("token", "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw")
T2_BOT_TOKEN = _BOTS.get("T2", {}).get("token", "8578781048:AAHCDrhqtH6gwcm1R3YZvNIu9zvAPM5Y5xU")
T3_BOT_TOKEN = _BOTS.get("T3", {}).get("token", "9288476562:AAEtFGf4kAfUS-tYmb6Lw-dulLEozwx_A5I")

# Backward-compatible aliases used across QuantNexus daemons
QUANT_ALERT_BOT_TOKEN = T1_BOT_TOKEN
NEXUS_AI_BOT_TOKEN = T2_BOT_TOKEN
NEXUS_GOLD_BOT_TOKEN = T3_BOT_TOKEN
TELEGRAM_BOT_TOKEN = T2_BOT_TOKEN
BOT_TOKEN = T2_BOT_TOKEN

SLEEVE_BOT_TOKENS = {
    "T1": T1_BOT_TOKEN,
    "T2": T2_BOT_TOKEN,
    "T3": T3_BOT_TOKEN,
}

ACCOUNT_BOT_TOKENS = {
    278062038: T1_BOT_TOKEN,
    278062039: T2_BOT_TOKEN,
    278062042: T3_BOT_TOKEN,
}

def get_bot_token_for_sleeve(sleeve: str) -> str:
    """Returns the dedicated bot token for T1, T2, or T3."""
    return SLEEVE_BOT_TOKENS.get(str(sleeve).upper().strip(), T2_BOT_TOKEN)

def get_bot_token_for_account(account_id: int) -> str:
    """Returns the dedicated bot token for a given MT5 account login."""
    return ACCOUNT_BOT_TOKENS.get(int(account_id), T2_BOT_TOKEN)
