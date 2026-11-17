import json
from datetime import datetime, timezone
from pathlib import Path

CALENDAR_PATH = Path(r"C:\Quant-Nexus-Eng\macro_calendar_utc.json")

# Map instruments to sensitive macro currencies
SYMBOL_CURRENCIES = {
    "EURUSD": {"USD", "EUR"},
    "GBPUSD": {"USD", "GBP"},
    "AUDUSD": {"USD", "AUD"},
    "USDCAD": {"USD", "CAD"},
    "USDJPY": {"USD", "JPY"},
    "GBPJPY": {"GBP", "JPY"},
    "XAUUSD": {"USD"},
    "BTCUSD": {"USD"},
}

# Default Tier-1 schedule (overridable via macro_calendar_utc.json)
DEFAULT_EVENTS = [
    {"name": "US Oct Advance Retail Sales", "currency": "USD", "utc": "2026-11-17T13:30:00+00:00", "pre_min": 15, "post_min": 5},
    {"name": "Fed Gov Waller Remarks",      "currency": "USD", "utc": "2026-11-17T14:10:00+00:00", "pre_min": 10, "post_min": 5},
]

def load_events() -> list[dict]:
    if CALENDAR_PATH.exists():
        try:
            data = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return DEFAULT_EVENTS

def check_macro_window(raw_symbol: str, now_utc: datetime | None = None) -> tuple[bool, str, float]:
    """
    Returns (is_blocked, reason, minutes_to_next_event).
    Blocks entries during [T - pre_min, T + post_min] for currencies affecting raw_symbol.
    """
    now = now_utc or datetime.now(timezone.utc)
    ccys = SYMBOL_CURRENCIES.get(raw_symbol.upper(), {"USD"})
    nearest_mins = 9999.0

    for ev in load_events():
        if ev.get("currency", "").upper() not in ccys:
            continue
        ev_dt = datetime.fromisoformat(ev["utc"])
        delta_mins = (ev_dt - now).total_seconds() / 60.0  # positive = upcoming, negative = passed
        pre_m = float(ev.get("pre_min", 15))
        post_m = float(ev.get("post_min", 5))

        if -post_m <= delta_mins <= pre_m:
            return True, f"MACRO-LOCK ({ev['name']} in {delta_mins:+.1f}m)", delta_mins
        if 0.0 < delta_mins < nearest_mins:
            nearest_mins = delta_mins

    return False, "CLEAR", nearest_mins
