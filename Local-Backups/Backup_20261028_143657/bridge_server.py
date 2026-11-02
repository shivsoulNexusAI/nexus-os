import os
import sys
import time
import logging
import MetaTrader5 as mt5

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("BridgeServer")

def main():
    if not mt5.initialize():
        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
        sys.exit(1)

    account_info = mt5.account_info()
    if account_info:
        logger.info(f"🔗 Bridge connected to MT5 Account: {account_info.login} ({account_info.server})")
    else:
        logger.warning("MT5 initialized, but no active account detected.")

    logger.info("⚡ Quant Nexus Bridge Server operational. Listening for tick synchronizations...")
    
    try:
        while True:
            # Heartbeat / IPC check cycle
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Bridge server terminating gracefully...")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
