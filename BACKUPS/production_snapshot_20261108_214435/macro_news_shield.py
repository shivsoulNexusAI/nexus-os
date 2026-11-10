r"""
QuantNexus Macro News Shield
Fetches and caches high-impact economic releases (USD, EUR, GBP, JPY).
Imposes hard execution lockout [-15min, +15min] around high-impact events.
Directory: C:\Quant-Nexus-Eng
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
import httpx

CACHE_FILE = Path(r"C:\Quant-Nexus-Eng\macro_calendar_cache.json")
BLACKOUT_MINUTES_BEFORE = 15
BLACKOUT_MINUTES_AFTER = 15

log = logging.getLogger("MacroNewsShield")

ASSET_CURRENCY_MAP = {
    "BTCUSD": ["USD"],
    "XAUUSD": ["USD"],
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "USDJPY": ["USD", "JPY"],
    "GBPJPY": ["GBP", "JPY"],
}

def fetch_macro_calendar(force_refresh: bool = False) -> list:
    now_utc = datetime.now(timezone.utc)
    if not force_refresh and CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            last_fetch = datetime.fromisoformat(data.get("last_fetched", "2000-01-01T00:00:00+00:00"))
            if now_utc - last_fetch < timedelta(hours=6):
                return data.get("events", [])
        except Exception as e:
            log.warning("Cache parse error: %s. Fetching fresh...", e)

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    events = []
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                raw_events = resp.json()
                for item in raw_events:
                    country = str(item.get("country", "")).upper()
                    impact = str(item.get("impact", "")).capitalize()
                    title = str(item.get("title", ""))
                    if country in ["USD", "EUR", "GBP", "JPY"] and impact == "High":
                        date_str = item.get("date")
                        if date_str:
                            events.append({
                                "title": title,
                                "currency": country,
                                "impact": impact,
                                "date": date_str
                            })
                log.info("Fetched %d High-Impact events from Economic Calendar.", len(events))
    except Exception as e:
        log.warning("Upstream calendar fetch failed (%s). Using cached/fallback events.", e)
        if CACHE_FILE.exists():
            try:
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                return data.get("events", [])
            except Exception:
                pass

    payload = {
        "last_fetched": now_utc.isoformat(),
        "events": events
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return events

def is_news_blackout(symbol: str, utc_now: datetime = None) -> tuple[bool, str]:
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
        
    currencies = ASSET_CURRENCY_MAP.get(symbol, ["USD"])
    events = fetch_macro_calendar(force_refresh=False)
    
    for ev in events:
        if ev.get("currency") in currencies:
            try:
                ev_time = datetime.fromisoformat(ev["date"]).astimezone(timezone.utc)
                delta_sec = (ev_time - utc_now).total_seconds()
                if -BLACKOUT_MINUTES_AFTER * 60 <= delta_sec <= BLACKOUT_MINUTES_BEFORE * 60:
                    mins_diff = delta_sec / 60.0
                    status = f"BEFORE release in {abs(mins_diff):.1f}m" if mins_diff >= 0 else f"AFTER release by {abs(mins_diff):.1f}m"
                    return True, f"NEWS_BLACKOUT: {ev['currency']} {ev['title']} ({status})"
            except Exception:
                continue

    return False, "NEWS_CLEAR"

if __name__ == "__main__":
    evs = fetch_macro_calendar(force_refresh=True)
    print(f"[+] Loaded {len(evs)} high-impact releases for fleet currencies.")
