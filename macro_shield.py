import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pytz

class MacroBlackoutShield:
    def __init__(self, blackout_minutes_before=15, blackout_minutes_after=10):
        self.pre_buffer = blackout_minutes_before
        self.post_buffer = blackout_minutes_after
        self.calendar_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        self.cached_events = []
        self.last_sync = None

    def fetch_high_impact_events(self):
        try:
            resp = requests.get(self.calendar_url, timeout=5)
            if resp.status_code != 200:
                return self.cached_events
            
            root = ET.fromstring(resp.content)
            events = []
            
            for item in root.findall('event'):
                impact = item.find('impact')
                currency = item.find('country')
                title = item.find('title')
                date_str = item.find('date')
                time_str = item.find('time')
                
                if impact is not None and impact.text == "High":
                    curr = currency.text if currency is not None else ""
                    if curr in ["USD", "EUR", "GBP", "JPY"]:
                        # Parse UTC timestamp
                        d = date_str.text if date_str is not None else ""
                        t = time_str.text if time_str is not None else ""
                        dt_raw = f"{d} {t}"
                        try:
                            # Calendar times are US Eastern
                            est = pytz.timezone('US/Eastern')
                            event_dt = est.localize(datetime.strptime(dt_raw, "%m-%d-%Y %I:%M%p"))
                            events.append({
                                "title": title.text if title is not None else "High Impact News",
                                "currency": curr,
                                "datetime_utc": event_dt.astimezone(pytz.utc),
                                "time_str": t
                            })
                        except Exception:
                            pass
            self.cached_events = events
            self.last_sync = datetime.now(timezone.utc)
            return events
        except Exception:
            return self.cached_events

    def audit_execution_gate(self, symbol="EURUSD"):
        now_utc = datetime.now(timezone.utc)
        if not self.cached_events or not self.last_sync or (now_utc - self.last_sync).total_seconds() > 3600:
            self.fetch_high_impact_events()
            
        sym_curr = [symbol[:3], symbol[3:]]
        
        for ev in self.cached_events:
            if ev['currency'] in sym_curr:
                diff_sec = (ev['datetime_utc'] - now_utc).total_seconds()
                diff_min = diff_sec / 60.0
                
                # Active Blackout Window (-15m to +10m)
                if -self.post_buffer <= diff_min <= self.pre_buffer:
                    return {
                        "allowed": False,
                        "status": "🔴 NEWS BLACKOUT ACTIVE",
                        "event": ev['title'],
                        "currency": ev['currency'],
                        "mins_remaining": round(diff_min, 1)
                    }
                # Warning Zone (Within 30m)
                elif 0 < diff_min <= 30:
                    return {
                        "allowed": True,
                        "status": f"🟡 PRE-NEWS BUFFER ({round(diff_min)}m to {ev['currency']} {ev['title'][:15]})",
                        "event": ev['title'],
                        "currency": ev['currency'],
                        "mins_remaining": round(diff_min, 1)
                    }
                    
        return {
            "allowed": True,
            "status": "🟢 CLEAR (NO HIGH-IMPACT THREATS)",
            "event": "None",
            "currency": "None",
            "mins_remaining": 999
        }

if __name__ == "__main__":
    shield = MacroBlackoutShield()
    shield.fetch_high_impact_events()
    res = shield.audit_execution_gate("EURUSD")
    print(f"Macro Gate Status: {res['status']}")
