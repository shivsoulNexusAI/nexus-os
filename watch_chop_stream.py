import time
import re
from pathlib import Path

log_path = Path(r"C:\Quant-Nexus-Eng\gold_hft.log")
pattern = re.compile(r"ATR \$([0-9.]+).*?CHOP ([0-9.]+)")

print("=" * 80)
print("LIVE CHOP & VOLATILITY SENTINEL MONITOR (Press Ctrl+C to Stop)")
print("=" * 80)

last_line = ""
try:
    while True:
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if lines and lines[-1] != last_line:
                last_line = lines[-1]
                match = pattern.search(last_line)
                if match:
                    atr, chop = float(match.group(1)), float(match.group(2))
                    status = "STANDOFF (CHOP LOCKOUT)" if chop >= 55.0 else ">>> ARMED (BREAKOUT MOMENTUM) <<<"
                    print(f"[{time.strftime('%H:%M:%S')}] ATR: ${atr:4.2f} | CHOP: {chop:4.1f} | State: {status}")
                elif "Placed Buy Stop" in last_line or "Placed Sell Stop" in last_line:
                    print(f"\a[{time.strftime('%H:%M:%S')}] [!] ACTIVE ORDER EVENT: {last_line}")
        time.sleep(5)
except KeyboardInterrupt:
    print("\n[*] Monitor paused.")