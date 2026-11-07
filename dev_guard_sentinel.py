"""
DEV GUARD SENTINEL (v3.1 Production Auto-Trim)
Systemic Resource Watchdog, Process Health Monitor, GC Tuner,
and Autonomous Win32 EmptyWorkingSet RAM Reclamation on 1GB VPS.
"""
import os
import gc
import sys
import time
import ctypes
import logging
import psutil
from datetime import datetime, timezone

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_telegram import send_alert

LOG_PATH = r"C:\Quant-Nexus-Eng\dev_guard_sentinel.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DevGuardSentinel")

POLL_INTERVAL_SEC = 15
RAM_ALERT_THRESHOLD_PCT = 85.0     # Trigger proactive trim if host RAM >= 85%
PER_PROCESS_MAX_MB = 120.0        # Alert if single python daemon > 120 MB
HEARTBEAT_INTERVAL_SEC = 3600      # 1 Hour
ALERT_COOLDOWN_SEC = 300           # 5 Minutes

# Enforce generational GC tuning for tight 1GB VPS footprint
gc.set_threshold(700, 10, 5)

# Win32 Process Rights for EmptyWorkingSet
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400

try:
    psapi = ctypes.WinDLL("psapi.dll")
    kernel32 = ctypes.WinDLL("kernel32.dll")
    WIN32_AVAILABLE = True
except Exception as e:
    logger.error(f"Failed to load psapi/kernel32 WinDLL: {e}")
    WIN32_AVAILABLE = False


class SentinelWatchdog:
    def __init__(self):
        self.last_heartbeat = time.time() - (HEARTBEAT_INTERVAL_SEC - 60)
        self.last_ram_alert = 0.0

    def purge_working_sets(self) -> tuple[float, float, int]:
        """Flushes idle working sets across MT5 terminals and Python runtimes."""
        if not WIN32_AVAILABLE:
            return 0.0, 0.0, 0

        before_total = 0.0
        after_total = 0.0
        trimmed_count = 0

        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                name = (p.info['name'] or '').lower()
                if 'terminal64' in name or 'python' in name:
                    pid = p.info['pid']
                    rss_before = p.info['memory_info'].rss / (1024**2)
                    before_total += rss_before

                    handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, pid)
                    if handle:
                        success = psapi.EmptyWorkingSet(handle)
                        kernel32.CloseHandle(handle)
                        if success:
                            trimmed_count += 1
                            try:
                                rss_after = psutil.Process(pid).memory_info().rss / (1024**2)
                                after_total += rss_after
                            except Exception:
                                after_total += rss_before
                        else:
                            after_total += rss_before
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return before_total, after_total, trimmed_count

    def audit_system_ram(self):
        vmem = psutil.virtual_memory()
        used_pct = vmem.percent
        used_mb = (vmem.total - vmem.available) / (1024**2)
        total_mb = vmem.total / (1024**2)

        if used_pct >= RAM_ALERT_THRESHOLD_PCT:
            now = time.time()
            if now - self.last_ram_alert > ALERT_COOLDOWN_SEC:
                self.last_ram_alert = now
                freed_gc = gc.collect()
                
                # Execute native Win32 working set purge
                before_ws, after_ws, count = self.purge_working_sets()
                saved_mb = max(0.0, before_ws - after_ws)
                
                vmem_after = psutil.virtual_memory()
                logger.warning(
                    f"⚠️ [RAM-PRESSURE] Usage: {used_pct:.1f}% -> Trimmed {count} processes | "
                    f"Freed: {saved_mb:.1f} MB | Post-Trim RAM: {vmem_after.percent:.1f}%"
                )

                send_alert(
                    "telegram_dev_guard_bot",
                    f"⚠️ <b>[AUTO-TRIM TRIGGERED]</b> VPS RAM Pressure\n"
                    f"• Initial Usage: <code>{used_pct:.1f}%</code> ({used_mb:.1f}/{total_mb:.1f} MB)\n"
                    f"• Win32 Purge: Trimmed <code>{count}</code> processes (Freed <code>{saved_mb:.1f} MB</code>)\n"
                    f"• GC Sweep: Freed <code>{freed_gc}</code> generational objects\n"
                    f"• Post-Trim RAM: <b>{vmem_after.percent:.1f}%</b> ({((vmem_after.total - vmem_after.available)/(1024**2)):.1f} MB)"
                )

    def audit_quant_daemons(self):
        for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
            try:
                p_name = p.info['name'] or ''
                if 'python' in p_name.lower():
                    cmd = ' '.join(p.info['cmdline'] or [])
                    for daemon in ['quantum_delta_daemon.py', 'deal_resolution_watcher.py', 'breakeven_engine.py']:
                        if daemon in cmd:
                            rss_mb = p.info['memory_info'].rss / (1024**2)
                            if rss_mb > PER_PROCESS_MAX_MB:
                                logger.warning(f"⚠️ [MEMORY-BLOAT] {daemon} (PID {p.info['pid']}) using {rss_mb:.2f} MB")
                                send_alert(
                                    "telegram_dev_guard_bot",
                                    f"⚠️ <b>[DAEMON MEMORY WARNING]</b>\n"
                                    f"• Daemon: <code>{daemon}</code> (PID {p.info['pid']})\n"
                                    f"• Working Set: <b>{rss_mb:.2f} MB</b> (Limit: {PER_PROCESS_MAX_MB} MB)"
                                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def dispatch_heartbeat_if_due(self):
        now = time.time()
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL_SEC:
            self.last_heartbeat = now
            vmem = psutil.virtual_memory()
            used_mb = (vmem.total - vmem.available) / (1024**2)
            total_mb = vmem.total / (1024**2)
            
            logger.info(f"💓 [HEARTBEAT] Dev Guard Sentinel OK | RAM: {vmem.percent}% ({used_mb:.1f} MB)")
            send_alert(
                "telegram_dev_guard_bot",
                f"🛡️ <b>[SENTINEL HEARTBEAT]</b> All Systems Nominal\n"
                f"• VPS RAM Usage: <code>{vmem.percent}%</code> ({used_mb:.1f} MB / {total_mb:.1f} MB)\n"
                f"• Auto-Trim Watchdog: <code>Active (>= 85.0%)</code>\n"
                f"• GC Governance: <code>700/10/5 Active</code>"
            )


def main():
    logger.info("Initializing Dev Guard Sentinel with Win32 Auto-Trimmer...")
    sentinel = SentinelWatchdog()
    logger.info("Sentinel loop running.")

    try:
        while True:
            sentinel.audit_system_ram()
            sentinel.audit_quant_daemons()
            sentinel.dispatch_heartbeat_if_due()
            gc.collect()
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Dev Guard Sentinel stopped by operator.")


if __name__ == "__main__":
    main()
