"""
Quant-Nexus Distributed Heartbeat & Failover Coordinator
=======================================================
Roles:
- PRIMARY (VPS): Writes continuous heartbeats with active lease lock.
- STANDBY (Local PC): Listens for heartbeat. Automatically engages local engine
  upon primary failure, and yields back to passive standby when primary recovers.
"""

import os
import sys
import time
import json
import socket
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [FAILOVER-DAEMON] %(message)s"
)
logger = logging.getLogger("FailoverCoordinator")

NODE_ROLE = os.getenv("QUANT_NODE_ROLE", "STANDBY")
HEARTBEAT_FILE = os.getenv("QUANT_HEARTBEAT_PATH", r"C:\Quant-Nexus-Backups\fleet_heartbeat.json")
FAILOVER_TIMEOUT_SEC = 45

class FailoverCoordinator:
    def __init__(self, role: str, heartbeat_path: str):
        self.role = role.upper()
        self.heartbeat_path = heartbeat_path
        self.hostname = socket.gethostname()
        self.is_active_executor = (self.role == "PRIMARY")

    def emit_heartbeat(self):
        payload = {
            "node_id": self.hostname,
            "role": self.role,
            "timestamp": time.time(),
            "datetime_utc": datetime.now(timezone.utc).isoformat(),
            "status": "HEALTHY",
            "active_executor": True
        }
        try:
            temp_path = f"{self.heartbeat_path}.tmp"
            with open(temp_path, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_path, self.heartbeat_path)
            logger.info(f"Heartbeat emitted by {self.hostname} ({self.role})")
        except Exception as e:
            logger.error(f"Failed to emit heartbeat: {e}")

    def inspect_primary_health(self) -> bool:
        if not os.path.exists(self.heartbeat_path):
            logger.warning("[!] No heartbeat anchor found. Presuming primary offline.")
            return False

        try:
            with open(self.heartbeat_path, "r") as f:
                data = json.load(f)
            last_ping = data.get("timestamp", 0)
            elapsed = time.time() - last_ping
            if elapsed > FAILOVER_TIMEOUT_SEC:
                logger.critical(f"[FAILOVER TRIGGER] Primary inactive for {elapsed:.1f}s (> {FAILOVER_TIMEOUT_SEC}s)!")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to read heartbeat anchor: {e}")
            return False

    def run_coordinator_loop(self):
        logger.info(f"[*] Starting Failover Coordinator on [{self.hostname}] in [{self.role}] mode.")
        
        while True:
            try:
                if self.role == "PRIMARY":
                    self.emit_heartbeat()
                    time.sleep(10)
                else:
                    primary_healthy = self.inspect_primary_health()
                    
                    if not primary_healthy and not self.is_active_executor:
                        logger.critical("[+] PROMOTING LOCAL NODE TO ACTIVE EXECUTOR.")
                        self.is_active_executor = True
                        os.system("nssm start ConnexxusCrypto247")
                        
                    elif primary_healthy and self.is_active_executor:
                        logger.info("[-] Primary VPS recovered. Demoting local node back to PASSIVE STANDBY.")
                        self.is_active_executor = False
                        os.system("nssm stop ConnexxusCrypto247")

                    time.sleep(15)

            except KeyboardInterrupt:
                logger.info("Coordinator stopped by user.")
                break
            except Exception as e:
                logger.error(f"Unhandled error in coordinator loop: {e}")
                time.sleep(5)

if __name__ == "__main__":
    role_arg = sys.argv[1] if len(sys.argv) > 1 else NODE_ROLE
    coordinator = FailoverCoordinator(role=role_arg, heartbeat_path=HEARTBEAT_FILE)
    coordinator.run_coordinator_loop()
