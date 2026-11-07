"""
QuantNexus Unified Async Telegram Dispatcher
Non-blocking, connection-pooled, low-memory IPC dispatcher.
"""
import os
import json
import logging
import asyncio
import threading
import httpx

CONFIG_PATH = r"C:\Quant-Nexus-Eng\master_telegram_trio.json"

class NexusNotifier:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(NexusNotifier, cls).__new__(cls)
                cls._instance._init_config()
        return cls._instance

    def _init_config(self):
        self.config = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                logging.error(f"[TELEGRAM-INIT-ERR] {e}")
        self.client = httpx.Client(timeout=4.0)

    def send_message(self, bot_role: str, text: str, parse_mode: str = "HTML"):
        """Fire-and-forget message dispatch running in an isolated background thread."""
        threading.Thread(target=self._dispatch_sync, args=(bot_role, text, parse_mode), daemon=True).start()

    def _dispatch_sync(self, bot_role: str, text: str, parse_mode: str):
        bot_cfg = self.config.get(bot_role)
        if not bot_cfg or not isinstance(bot_cfg, dict):
            logging.error(f"[TELEGRAM] Bot role '{bot_role}' not found in configuration.")
            return

        token = bot_cfg.get("token")
        chat_id = bot_cfg.get("chat_id") or self.config.get("chat_id")
        if not token or not chat_id:
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            res = self.client.post(url, json=payload)
            if res.status_code != 200:
                logging.warning(f"[TELEGRAM-WARN] {bot_role} failed ({res.status_code}): {res.text}")
        except Exception as e:
            logging.debug(f"[TELEGRAM-TIMEOUT] Discarded telemetry to preserve 5ms execution: {e}")

notifier = NexusNotifier()

def send_alert(bot_role: str, text: str):
    notifier.send_message(bot_role, text)