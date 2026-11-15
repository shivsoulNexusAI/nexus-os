import os

import sys

import time

import json

import logging

from datetime import datetime, timedelta

from pathlib import Path

import numpy as np

import MetaTrader5 as mt5



BASE_DIR = Path(r"C:\Quant-Nexus-Eng")

STATE_FILE = BASE_DIR / "microstructure_state.json"

TEMP_STATE_FILE = BASE_DIR / "microstructure_state.tmp"

LOG_FILE = BASE_DIR / "microstructure_sentinel.log"

TERMINAL_PATH = r"C:/MT5_Quant_278061453/terminal64.exe"



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s [%(levelname)s] [MICRO-SENTINEL] %(message)s",

    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)]

)

logger = logging.getLogger("MicrostructureSentinel")



SYMBOLS = {

    "XAUUSD": {"step_mult": 25, "lookback_sec": 300, "delta_hurdle": 18.0},  # $0.25 VPOC bins

    "BTCUSD": {"step_mult": 100, "lookback_sec": 300, "delta_hurdle": 18.0}, # $1.00 VPOC bins

    "US30":   {"step_mult": 20, "lookback_sec": 300, "delta_hurdle": 20.0},

    "EURUSD": {"step_mult": 5,  "lookback_sec": 300, "delta_hurdle": 22.0},

    "GBPUSD": {"step_mult": 5,  "lookback_sec": 300, "delta_hurdle": 22.0},

    "USDCHF": {"step_mult": 5,  "lookback_sec": 300, "delta_hurdle": 22.0},

    "USDCAD": {"step_mult": 5,  "lookback_sec": 300, "delta_hurdle": 22.0},

}



def analyze_symbol_microstructure(symbol: str, cfg: dict) -> dict | None:

    sym_info = mt5.symbol_info(symbol)

    if not sym_info:

        return None



    now = datetime.now()

    start = now - timedelta(seconds=cfg["lookback_sec"])

    ticks = mt5.copy_ticks_range(symbol, start, now, mt5.COPY_TICKS_ALL)

    if ticks is None or len(ticks) < 15:

        return None



    bids = ticks["bid"].astype(np.float64)

    asks = ticks["ask"].astype(np.float64)

    vols = ticks["volume_ext"].astype(np.float64) if "volume_ext" in ticks.dtype.names else ticks["volume"].astype(np.float64)

    vols = np.where(vols > 0, vols, 1.0)



    # True Quote-Shift Tick Rule (immune to Exness OTC TICK_FLAG_BUY false positives)

    d_bid = np.diff(bids)

    d_ask = np.diff(asks)

    mid_shift = (d_bid + d_ask) * 0.5

    step_vols = vols[1:]



    buy_vol = float(np.sum(step_vols[mid_shift > 0]))

    sell_vol = float(np.sum(step_vols[mid_shift < 0]))

    neutral_vol = float(np.sum(step_vols[mid_shift == 0]))



    net_delta = buy_vol - sell_vol

    active_vol = buy_vol + sell_vol

    delta_pct = (net_delta / active_vol * 100.0) if active_vol > 0 else 0.0



    # Discretized Volume Profile (VPOC, 70% VAH / VAL)

    point = sym_info.point

    digits = sym_info.digits

    step = point * cfg["step_mult"]

    binned_prices = np.round(np.round(bids[1:] / step) * step, digits)



    unique_prices, inv_idx = np.unique(binned_prices, return_inverse=True)

    bin_vols = np.bincount(inv_idx, weights=step_vols)



    poc_idx = int(np.argmax(bin_vols))

    vpoc = float(unique_prices[poc_idx])



    total_vol = float(np.sum(bin_vols))

    target_va = total_vol * 0.70

    va_vol = float(bin_vols[poc_idx])

    left, right = poc_idx, poc_idx



    while va_vol < target_va and (left > 0 or right < len(unique_prices) - 1):

        v_left = float(bin_vols[left - 1]) if left > 0 else -1.0

        v_right = float(bin_vols[right + 1]) if right < len(unique_prices) - 1 else -1.0

        if v_right >= v_left and v_right >= 0:

            right += 1

            va_vol += v_right

        elif v_left >= 0:

            left -= 1

            va_vol += v_left

        else:

            break



    val = float(unique_prices[left])

    vah = float(unique_prices[right])

    current_mid = float((bids[-1] + asks[-1]) * 0.5)



    # Anti-Chop POC Gate: price trapped inside tight 1.5-bin core of VPOC

    inside_poc_chop = abs(current_mid - vpoc) <= (step * 1.5)



    hurdle = cfg["delta_hurdle"]

    if delta_pct >= hurdle:

        regime = "STRONG_BULLISH_DELTA"

    elif delta_pct <= -hurdle:

        regime = "STRONG_BEARISH_DELTA"

    else:

        regime = "BALANCED_CHOP"



    return {

        "vpoc": round(vpoc, digits),

        "val": round(val, digits),

        "vah": round(vah, digits),

        "current_mid": round(current_mid, digits),

        "inside_poc_chop": bool(inside_poc_chop),

        "ticks": int(len(ticks)),

        "buy_vol": round(buy_vol, 2),

        "sell_vol": round(sell_vol, 2),

        "net_delta": round(net_delta, 2),

        "delta_pct": round(delta_pct, 2),

        "regime": regime

    }



def main():

    if not mt5.initialize(path=TERMINAL_PATH, portable=False):

        logger.error(f"MT5 init failed: {mt5.last_error()}")

        return



    logger.info("MICROSTRUCTURE SENTINEL ARMED (Quote-Shift Delta + 5m VPOC/VAH/VAL)")

    cycle = 0

    while True:

        try:

            t0 = time.perf_counter()

            payload = {"timestamp": datetime.now().isoformat(), "fleet": {}}

            for sym, cfg in SYMBOLS.items():

                res = analyze_symbol_microstructure(sym, cfg)

                if res:

                    payload["fleet"][sym] = res



            with open(TEMP_STATE_FILE, "w", encoding="utf-8") as f:

                json.dump(payload, f, indent=2)

            TEMP_STATE_FILE.replace(STATE_FILE)



            ms = (time.perf_counter() - t0) * 1000.0

            if cycle % 30 == 0:

                xau = payload["fleet"].get("XAUUSD", {})

                logger.info(f"[HEARTBEAT] {ms:.1f}ms | XAUUSD VPOC={xau.get('vpoc')} | Delta={xau.get('delta_pct')}% ({xau.get('regime')}) | Chop={xau.get('inside_poc_chop')}")

            cycle += 1

            time.sleep(1.5)

        except KeyboardInterrupt:

            break

        except Exception as e:

            logger.error(f"Loop error: {e}")

            time.sleep(2.0)

    mt5.shutdown()



if __name__ == "__main__":

    main()

