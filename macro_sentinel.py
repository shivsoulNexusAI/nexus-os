import urllib.request
import json
import datetime

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def fetch_macro_freeze_status(window_minutes=30) -> tuple[bool, str]:
    """
    Checks for high-impact USD economic releases within +/- window_minutes.
    Returns (freeze_active: bool, reason: str).
    """
    try:
        req = urllib.request.Request(
            FF_CALENDAR_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        now = datetime.datetime.now(datetime.timezone.utc)

        for event in data:
            if event.get("impact") == "High" and event.get("country") in ["USD", "ALL"]:
                dt_str = event.get("date")
                if dt_str:
                    try:
                        event_time = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                        delta = (event_time - now).total_seconds() / 60.0
                        if -window_minutes <= delta <= window_minutes:
                            title = event.get("title", "High-Impact USD News")
                            return True, f"{title} (in {delta:+.1f}m)"
                    except Exception:
                        continue
                        
        return False, "CLEARED: No High-Impact USD News Near Window"
    except Exception as e:
        return False, f"CALENDAR OFFLINE ({str(e)[:30]})"

if __name__ == "__main__":
    frozen, reason = fetch_macro_freeze_status()
    print(f"Macro Freeze Active: {frozen} | Status: {reason}")