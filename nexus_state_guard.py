"""
QUANTNEXUS ATOMIC STATE GUARD (v1.0 Production)
Hardened atomic file transactions, corruption recovery, and schema-validated
reads/writes for risk_state.json on Windows environments.
"""
import os
import sys
import json
import time
import shutil
import random
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("NexusStateGuard")

STATE_FILE_PATH = r"C:\Quant-Nexus-Eng\risk_state.json"
BACKUP_FILE_PATH = r"C:\Quant-Nexus-Eng\risk_state.json.bak"

REQUIRED_STATE_SCHEMA = {
    "circuit_breaker_tripped": bool,
    "daily_loss_pct": (int, float),
    "peak_balance": (int, float),
    "current_balance": (int, float),
    "drawdown_threshold": (int, float),
    "last_updated_utc": str
}

DEFAULT_FALLBACK_STATE = {
    "circuit_breaker_tripped": False,
    "daily_loss_pct": 0.0,
    "peak_balance": 1000.0,
    "current_balance": 1000.0,
    "drawdown_threshold": 5.0,
    "consecutive_losses": 0,
    "active_circuit_reason": "NONE",
    "last_updated_utc": datetime.now(timezone.utc).isoformat()
}

def validate_schema(data: Dict[str, Any]) -> bool:
    """Verifies that mandatory operational keys and data types exist."""
    if not isinstance(data, dict):
        return False
    for key, expected_type in REQUIRED_STATE_SCHEMA.items():
        if key not in data:
            logger.error(f"State validation error: missing mandatory key '{key}'")
            return False
        if not isinstance(data[key], expected_type):
            logger.error(f"State validation error: key '{key}' expected {expected_type}, got {type(data[key])}")
            return False
    return True

def read_risk_state(file_path: str = STATE_FILE_PATH, max_retries: int = 8) -> Dict[str, Any]:
    """
    Reads risk state with collision backoff and automatic corrupted file rollback.
    """
    if not os.path.exists(file_path):
        logger.warning(f"State file {file_path} missing. Initializing default fallback state.")
        write_risk_state(DEFAULT_FALLBACK_STATE, file_path=file_path)
        return DEFAULT_FALLBACK_STATE.copy()

    for attempt in range(max_retries):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if validate_schema(data):
                return data
            else:
                raise ValueError("Corrupted or incomplete schema detected in risk_state.json")

        except (json.JSONDecodeError, ValueError, PermissionError) as ex:
            if attempt < max_retries - 1:
                sleep_dur = 0.02 * (2 ** attempt) + random.uniform(0.005, 0.015)
                time.sleep(sleep_dur)
            else:
                logger.critical(f"FATAL: Read failure after {max_retries} attempts: {ex}")
                # Attempt rollback from backup file if available
                if os.path.exists(BACKUP_FILE_PATH):
                    try:
                        with open(BACKUP_FILE_PATH, "r", encoding="utf-8") as bf:
                            backup_data = json.load(bf)
                        if validate_schema(backup_data):
                            logger.info("[RECOVERY] Successfully rolled back state from risk_state.json.bak")
                            return backup_data
                    except Exception as b_ex:
                        logger.error(f"Failed to read backup state file: {b_ex}")

                logger.warning("[FALLBACK] Emitting emergency fail-safe default state.")
                return DEFAULT_FALLBACK_STATE.copy()

    return DEFAULT_FALLBACK_STATE.copy()

def write_risk_state(new_state: Dict[str, Any], file_path: str = STATE_FILE_PATH, max_retries: int = 8) -> bool:
    """
    Atomically writes risk state using isolated temp file staging and os.replace().
    """
    if not validate_schema(new_state):
        logger.error("State write rejected: proposed payload violates state schema.")
        return False

    # Stamp update timestamp
    new_state["last_updated_utc"] = datetime.now(timezone.utc).isoformat()
    serialized = json.dumps(new_state, indent=2)

    base_dir = os.path.dirname(os.path.abspath(file_path))
    temp_path = os.path.join(base_dir, f".risk_state.tmp.{os.getpid()}_{time.time_ns()}")

    # 1. Staging write & flush to physical medium
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex:
        logger.error(f"Failed to stage atomic state temp file: {ex}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False

    # 2. Atomic OS replace with collision retry
    for attempt in range(max_retries):
        try:
            # Maintain an authoritative backup copy right before replacing
            if os.path.exists(file_path):
                try:
                    shutil.copy2(file_path, BACKUP_FILE_PATH)
                except Exception:
                    pass

            os.replace(temp_path, file_path)
            return True
        except PermissionError:
            if attempt < max_retries - 1:
                sleep_dur = 0.02 * (2 ** attempt) + random.uniform(0.005, 0.015)
                time.sleep(sleep_dur)
            else:
                logger.error(f"Failed atomic os.replace on {file_path} after {max_retries} attempts.")
        except Exception as ex:
            logger.error(f"Unexpected error during atomic state swap: {ex}")
            break

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass
    return False

if __name__ == "__main__":
    print("=== TESTING ATOMIC STATE GUARD ===")
    state = read_risk_state()
    print("[+] Successfully read state:")
    print(json.dumps(state, indent=2))
    
    print("\n[*] Testing atomic transaction write...")
    state["consecutive_losses"] = state.get("consecutive_losses", 0)
    success = write_risk_state(state)
    print(f"[+] State written successfully: {success}")
    print("==================================")
