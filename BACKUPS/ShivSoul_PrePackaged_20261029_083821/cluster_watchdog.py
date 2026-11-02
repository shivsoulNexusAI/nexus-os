"""
Quant Nexus: Real-Time Cluster Telemetry Watchdog with Audio Alerts
Pulls telemetry every 3 seconds from VPS over Tailscale (100.116.213.49).
Includes acoustic warnings for connection loss and equity threshold breaches.
"""

import time
import requests
import winsound
from datetime import datetime

VPS_URL = "http://100.116.213.49:8088/health"

# --- RISK THRESHOLDS ---
EQUITY_MIN_THRESHOLD = 950.00   # Triggers alarm if equity falls below this level
MAX_DRAWDOWN_PCT_ALERT = 3.00   # Triggers alarm if session drawdown exceeds 3%

def sound_alert(freq=1200, duration=350):
    """Play alert tone asynchronously without blocking UI loop."""
    try:
        winsound.Beep(freq, duration)
    except Exception:
        pass

def sound_critical():
    """Double-tone siren for severe equity or disconnect violations."""
    try:
        winsound.Beep(1800, 200)
        winsound.Beep(900, 250)
    except Exception:
        pass

def format_row(ticket, symbol, pos_type, volume, profit):
    p_color = "\033[92m" if profit >= 0 else "\033[91m"
    reset = "\033[0m"
    return f"  | {ticket:<10} | {symbol:<8} | {pos_type:<4} | {volume:<4.2f} | {p_color}${profit:>7.2f}{reset} |"

def main():
    peak_equity = 0.0
    print(f"[*] Initializing connection to {VPS_URL}...")
    
    while True:
        try:
            res = requests.get(VPS_URL, timeout=3)
            if res.status_code == 200:
                data = res.json()
                acc = data.get("account", {})
                positions = data.get("positions", [])
                pos_count = data.get("open_positions_count", 0)
                ts = data.get("timestamp_utc", "")
                
                equity = float(acc.get("equity", 0.0))
                balance = float(acc.get("balance", 0.0))
                free_margin = float(acc.get("free_margin", 0.0))
                
                # Session peak equity tracking
                if equity > peak_equity:
                    peak_equity = equity
                
                drawdown_pct = ((peak_equity - equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0
                
                # Check threshold breaches
                equity_breach = equity < EQUITY_MIN_THRESHOLD
                drawdown_breach = drawdown_pct >= MAX_DRAWDOWN_PCT_ALERT
                
                # Trigger sound alerts on breach
                if equity_breach or drawdown_breach:
                    sound_critical()
                
                # Clear terminal and render dashboard
                print("\033[H\033[J", end="")
                print("=" * 64)
                print(f" QUANT NEXUS TELEMETRY BRIDGE | NODE: {data.get('cluster_node')}")
                print(f" MT5 Status: {'ONLINE' if data.get('mt5_connected') else 'DISCONNECTED'} | Server UTC: {ts[:19]}")
                print("-" * 64)
                
                # Equity status line with breach highlight
                eq_color = "\033[91m" if equity_breach else "\033[92m"
                reset = "\033[0m"
                print(f" Balance: ${balance:.2f}  |  Equity: {eq_color}${equity:.2f}{reset}  |  Free: ${free_margin:.2f}")
                print(f" Active Slots: {pos_count}/4      |  Peak: ${peak_equity:.2f}  |  DD: {drawdown_pct:.2f}%")
                
                if equity_breach:
                    print(f" \033[41m\033[97m [!] ALERT: EQUITY BREACHED MIN THRESHOLD (${EQUITY_MIN_THRESHOLD:.2f}) \033[0m")
                if drawdown_breach:
                    print(f" \033[41m\033[97m [!] ALERT: MAX DRAWDOWN TRIGGERED (>{MAX_DRAWDOWN_PCT_ALERT:.1f}%) \033[0m")
                    
                print("-" * 64)
                if positions:
                    print("  | Ticket     | Symbol   | Side | Lot  | Profit    |")
                    print("  |------------|----------|------|------|-----------|")
                    for p in positions:
                        print(format_row(p['ticket'], p['symbol'], p['type'], p['volume'], p['profit']))
                else:
                    print("  [!] No open positions currently in slots.")
                print("=" * 64)
                print(f" Last Polled: {datetime.now().strftime('%H:%M:%S')} (Interval: 3s | Min Equity: ${EQUITY_MIN_THRESHOLD:.2f})")
            else:
                sound_alert(600, 400)
                print(f"\n[!] VPS Error Response: HTTP {res.status_code}")
        except requests.exceptions.RequestException as e:
            sound_alert(500, 600)
            print(f"\n[!] CONNECTION LOST: VPS unreachable via Tailscale. Retrying... ({e})")
            
        time.sleep(3)

if __name__ == "__main__":
    main()