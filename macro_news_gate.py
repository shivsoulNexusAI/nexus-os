# -*- coding: utf-8 -*-
"""
QUANT-NEXUS v11.1 MACRO ECONOMIC NEWS BLACKOUT GATE (USD TIER-1: NFP / CPI / FOMC)
Dual-layer protection:
1. Deterministic NFP (1st Friday 13:15-13:45 UTC) + 2026-2027 CPI & FOMC schedule
2. Optional 6-hour cached ForexFactory USD High-Impact JSON feed (non-blocking fallback)
"""
import json
import calendar
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

CACHE_PATH = Path(r"C:\Quant-Nexus-Eng\macro_calendar_cache.json")
FF_FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Scheduled Tier-1 USD CPI dates (13:30 UTC release -> blackout 13:15-13:45 UTC)
CPI_DATES_UTC = {
    "2026-11-12", "2026-12-10",
    "2027-01-13", "2027-02-10", "2027-03-10", "2027-04-13",
    "2027-05-12", "2027-06-10", "2027-07-14", "2027-08-11",
    "2027-09-14", "2027-10-13", "2027-11-10", "2027-12-10",
}

# Scheduled FOMC Rate Decision dates (19:00 UTC statement + 19:30 presser -> blackout 18:45-20:00 UTC)
FOMC_DATES_UTC = {
    "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
    "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
}

def _is_first_friday(dt_utc: datetime) -> bool:
    return dt_utc.weekday() == calendar.FRIDAY and 1 <= dt_utc.day <= 7

def _refresh_ff_cache_if_stale(now_utc: datetime) -> list[dict]:
    try:
        if CACHE_PATH.exists():
            mtime = datetime.fromtimestamp(CACHE_PATH.stat().st_mtime, tz=timezone.utc)
            if (now_utc - mtime).total_seconds() < 21600:  # 6 hours
                return json.loads(CACHE_PATH.read_text(encoding="utf-8"))

        req = urllib.request.Request(FF_FEED_URL, headers={"User-Agent": "QuantNexus/11.1"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        usd_high = [
            ev for ev in raw
            if str(ev.get("country", "")).upper() == "USD"
            and str(ev.get("impact", "")).lower() == "high"
        ]
        CACHE_PATH.write_text(json.dumps(usd_high, indent=2), encoding="utf-8")
        return usd_high
    except Exception:
        if CACHE_PATH.exists():
            try:
                return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

def check_usd_macro_blackout(now_utc: datetime | None = None) -> tuple[bool, str]:
    """
    Returns (is_blackout: bool, reason: str).
    Blocks new entries & pending breakout orders T-15m to T+15m around Tier-1 USD releases.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    d_str = now_utc.strftime("%Y-%m-%d")
    mins = now_utc.hour * 60 + now_utc.minute

    # 1. Deterministic NFP (First Friday of month, 13:30 UTC -> 13:15 to 13:45 UTC)
    if _is_first_friday(now_utc) and (13 * 60 + 15) <= mins <= (13 * 60 + 45):
        return True, "USD_NFP_BLACKOUT (13:15-13:45 UTC)"

    # 2. Deterministic US CPI (13:30 UTC -> 13:15 to 13:45 UTC)
    if d_str in CPI_DATES_UTC and (13 * 60 + 15) <= mins <= (13 * 60 + 45):
        return True, f"USD_CPI_BLACKOUT ({d_str} 13:15-13:45 UTC)"

    # 3. Deterministic FOMC Statement & Press Conference (18:45 to 20:00 UTC)
    if d_str in FOMC_DATES_UTC and (18 * 60 + 45) <= mins <= (20 * 60 + 0):
        return True, f"USD_FOMC_BLACKOUT ({d_str} 18:45-20:00 UTC)"

    # 4. Dynamic Weekly Feed Check (T-15m to T+15m around any High-Impact USD event)
    events = _refresh_ff_cache_if_stale(now_utc)
    for ev in events:
        dt_raw = ev.get("date")
        if not dt_raw:
            continue
        try:
            ev_dt = datetime.fromisoformat(str(dt_raw)).astimezone(timezone.utc)
            delta_sec = (now_utc - ev_dt).total_seconds()
            if -900 <= delta_sec <= 900:
                title = str(ev.get("title", "USD_HIGH_IMPACT"))
                return True, f"USD_NEWS_BLACKOUT ({title} @ {ev_dt.strftime('%H:%M UTC')})"
        except Exception:
            continue

    return False, ""

if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    blocked, why = check_usd_macro_blackout(now)
    nfp_test, nfp_why = check_usd_macro_blackout(datetime(2026, 12, 4, 13, 28, tzinfo=timezone.utc))
    fomc_test, fomc_why = check_usd_macro_blackout(datetime(2026, 12, 9, 19, 10, tzinfo=timezone.utc))
    print(f"[LIVE NOW {now.strftime('%Y-%m-%d %H:%M UTC')}] Blackout={blocked} | Reason='{why}'")
    print(f"[SELF-TEST NFP 2026-12-04 13:28 UTC] Blackout={nfp_test} | Reason='{nfp_why}'")
    print(f"[SELF-TEST FOMC 2026-12-09 19:10 UTC] Blackout={fomc_test} | Reason='{fomc_why}'")
