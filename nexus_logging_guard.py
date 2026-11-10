"""
QUANTNEXUS LOGGING GUARD (v1.0 Production)
Enforces strict 5MB rotating file handlers with dual-backup retention
to prevent VPS disk block saturation and pagefile starvation.
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB hard file cap
BACKUP_COUNT = 2                 # 2 rolling archive files (.1, .2)

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"

def get_rotating_logger(
    logger_name: str,
    log_filename: str,
    level: int = logging.INFO,
    format_str: str = DEFAULT_FORMAT
) -> logging.Logger:
    """
    Configures and returns a Logger with an atomic, bounded RotatingFileHandler
    and an unbuffered stdout StreamHandler.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # Avoid duplicate handlers on re-initialization
    if logger.handlers:
        return logger

    formatter = logging.Formatter(format_str)

    # Ensure log directory exists
    base_dir = r"C:\Quant-Nexus-Eng"
    if not os.path.exists(base_dir):
        base_dir = os.path.dirname(os.path.abspath(__file__))

    full_log_path = os.path.join(base_dir, log_filename)

    # 1. Bounded 5MB Rotating File Handler
    rf_handler = RotatingFileHandler(
        full_log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
        delay=True  # Opens file only on first emission
    )
    rf_handler.setFormatter(formatter)
    rf_handler.setLevel(level)
    logger.addHandler(rf_handler)

    # 2. Standard Output Stream Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger

if __name__ == "__main__":
    test_logger = get_rotating_logger("TestLogger", "test_rotation.log")
    test_logger.info("Testing QuantNexus Rotating Logger initialization.")
    print(f"[+] nexus_logging_guard initialized: maxBytes={MAX_LOG_BYTES}, backupCount={BACKUP_COUNT}")
