# -*- coding: utf-8 -*-
"""
SHIVSOUL QUANTITATIVE DESK - MACRO NEWS CIRCUIT BREAKER
Scrapes, parses, and caches High-Impact (Red-Folder) macroeconomic releases.
Locks trading executions 30 minutes before and after high-volatility events.
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone
import requests

CACHE_FILE = "news_cache.json"
CACHE_TTL_HOURS = 4
BUFFER_MINUTES = 30  # 30-minute pre/post release blackout

# ForexFactory public weekly JSON endpoint
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

CURRENCY_MAPPING = {
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "USDJPY": ["USD", "JPY"],
    "XAUUSD": ["USD"],
    "BTCUSD": ["USD"],
    "US30": ["USD"],
    "NAS100": ["USD"],
    "USOIL": ["USD"]
}

class MacroNewsShield:
    def __init__(self, buffer_minutes: int = BUFFER_MINUTES):
        self.buffer = timedelta(minutes=buffer_minutes)
        self.events = self._load_or_refresh_events()

    def _load_or_refresh_events(self):
        """Loads cached events from disk or downloads a fresh calendar."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cached_time = data.get("timestamp", 0)
                    if time.time() - cached_time < (CACHE_TTL_HOURS * 3600):
                        return data.get("events", [])
            except Exception as e:
                print(f"[-] Cache read exception: {e}")

        return self.fetch_fresh_calendar()

    def fetch_fresh_calendar(self):
        """Pulls the high-impact calendar from the network and updates the cache."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            resp = requests.get(CALENDAR_URL, headers=headers, timeout=10)
            if resp.status_code == 200:
                raw_data = resp.json()
                parsed_events = []
                for item in raw_data:
                    # Filter for High Impact (Red-Folder) items only
                    if item.get("impact") == "High":
                        # Format is ISO string e.g. "2026-10-23T08:30:00-04:00"
                        parsed_events.append({
                            "title": item.get("title", ""),
                            "country": item.get("country", ""),
                            "date": item.get("date", ""),
                            "impact": item.get("impact", "")
                        })

                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"timestamp": time.time(), "events": parsed_events}, f, indent=2)

                print(f"[+] News Shield: Cached {len(parsed_events)} High-Impact macro events.")
                return parsed_events
        except Exception as e:
            print(f"[-] Could not update economic calendar: {e}")
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f).get("events", [])
                except Exception:
                    pass
        return []

    def is_symbol_blocked(self, symbol: str) -> tuple[bool, str, dict | None]:
        """
        Determines whether a symbol is locked due to an impending or recent Red-Folder event.
        Returns: (is_blocked: bool, reason_str: str, event_data: dict)
        """
        currencies = CURRENCY_MAPPING.get(symbol, ["USD"])
        now_utc = datetime.now(timezone.utc)

        for ev in self.events:
            if ev.get("country") in currencies:
                try:
                    ev_time = datetime.fromisoformat(ev["date"])
                    if ev_time.tzinfo is None:
                        ev_time = ev_time.replace(tzinfo=timezone.utc)

                    window_start = ev_time - self.buffer
                    window_end = ev_time + self.buffer

                    if window_start <= now_utc <= window_end:
                        mins_left = (ev_time - now_utc).total_seconds() / 60.0
                        if mins_left > 0:
                            reason = f"RED FOLDER: '{ev['title']}' ({ev['country']}) in {mins_left:.0f} mins"
                        else:
                            reason = f"POST-NEWS VOLATILITY: '{ev['title']}' ({abs(mins_left):.0f} mins ago)"
                        return True, reason, ev
                except Exception:
                    continue

        return False, "CLEAR", None

if __name__ == "__main__":
    shield = MacroNewsShield()
    print("\n--- MACRO NEWS SHIELD AUDIT (High-Impact Releases) ---")
    
    test_symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
    for sym in test_symbols:
        blocked, reason, ev = shield.is_symbol_blocked(sym)
        status_tag = "🛑 BLOCKED" if blocked else "✅ CLEAR"
        print(f"[{sym}] {status_tag} | Status: {reason}")