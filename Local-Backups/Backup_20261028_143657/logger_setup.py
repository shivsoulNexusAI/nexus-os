import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler

def setup_daemon_logger(
    daemon_name: str,
    log_dir: str = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot\logs",
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
    log_level: int = logging.INFO
) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{daemon_name}.log")

    logger = logging.getLogger(daemon_name)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s UTC [%(levelname)s] (%(name)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.Formatter.converter = lambda *args: time.gmtime(*args)

    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
