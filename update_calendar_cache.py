# -*- coding: utf-8 -*-
"""
FOREXFACTORY ECONOMIC CALENDAR INGESTOR
Fetches current week JSON feed and updates C:/Quant-Nexus-Eng/ff_calendar_cache.json
"""
import json
from pathlib import Path
import urllib.request

CACHE_FILE = Path(r"C:\Quant-Nexus-Eng\ff_calendar_cache.json")
URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def fetch_calendar():
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                raw = response.read().decode("utf-8")
                events = json.loads(raw)
                CACHE_FILE.write_text(json.dumps(events, indent=2), encoding="utf-8")
                print(f"[+] Successfully cached {len(events)} economic events to {CACHE_FILE}")
                return True
    except Exception as e:
        print(f"[-] Calendar fetch failed: {e}")
    return False

if __name__ == "__main__":
    fetch_calendar()