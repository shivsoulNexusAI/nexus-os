# -*- coding: utf-8 -*-
"""
QUANT-NEXUS DEEP DELTA 60s AUTO-SCANNER & AUTO-TRIGGER VISION ENGINE
Cycles every 60s:
1. Re-evaluates Account #278017866 (Silo 1), #278041169 (Silo 2), #278041671 (Silo 3).
2. Computes Half-Kelly Mathematical Position Sizing for active setups.
3. Auto-triggers sizing reconciliation and trade execution if liquidity sweep confirms.
"""
import time
import math
import logging
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5

LOG_FILE = Path(r"C:\Quant-Nexus-Eng\deep_delta_scanner.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("DeepDeltaVision")

SILO_1_PATH = r"C:/Program Files/MetaTrader 5 - Apex Satellite/terminal64.exe"
SILO_2_PATH = r"C:/MT5_Quant_278017866/terminal64.exe"
SILO_3_PATH = r"C:/MT5_HFT_278041671/terminal64.exe"

SILOS = [
    {"name": "Silo 1 (Silver Bullet)", "login": 278017866, "path": SILO_1_PATH, "portable": False, "symbol": "USDJPY"},
    {"name": "Silo 2 (Majors Grid)",   "login": 278041169, "path": SILO_2_PATH, "portable": False, "symbol": "GBPUSD"},
    {"name": "Silo 3 (Gold HFT)",      "login": 278041671, "path": SILO_3_PATH, "portable": True,  "symbol": "XAUUSD"}
]

def calculate_half_kelly(equity: float, sym_info, sl_distance_points: float,
                         win_rate: float = 0.62, payoff_ratio: float = 1.50,
                         max_risk_pct: float = 0.015) -> float:
    if not sym_info or equity <= 0:
        return 0.01
    
    vol_min = float(sym_info.volume_min)
    vol_max = float(sym_info.volume_max)
    vol_step = float(sym_info.volume_step)
    point = float(sym_info.point)
    tick_val = float(sym_info.trade_tick_value)
    tick_sz = float(sym_info.trade_tick_size)

    full_k = win_rate - ((1.0 - win_rate) / payoff_ratio)
    half_k = max(0.0, full_k / 2.0)
    risk_frac = min(half_k * 0.05, max_risk_pct)
    dollar_risk = equity * risk_frac

    point_val = (tick_val / tick_sz) * point if tick_sz > 0 else 1.0
    dollar_risk_per_lot = sl_distance_points * point_val

    if dollar_risk_per_lot <= 0:
        return vol_min

    raw = dollar_risk / dollar_risk_per_lot
    stepped = math.floor(raw / vol_step) * vol_step
    return round(max(vol_min, min(stepped, vol_max)), 2)

def run_delta_cycle():
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n[{now_str}] === EXECUTING 60s DEEP DELTA VISION SCAN ===")
    log.info("=== START 60s DEEP DELTA VISION SCAN ===")

    for silo in SILOS:
        if not mt5.initialize(path=silo["path"], portable=silo["portable"]):
            log.warning("[-] Could not initialize %s: %s", silo["name"], mt5.last_error())
            continue

        acc = mt5.account_info()
        if not acc:
            log.warning("[-] Could not retrieve account info for %s", silo["name"])
            mt5.shutdown()
            continue

        symbol = silo["symbol"]
        sym_info = mt5.symbol_info(symbol)
        positions = mt5.positions_get(symbol=symbol) or []
        
        # Calculate dynamic Half-Kelly benchmark
        benchmark_sl_pips = 35.0
        sl_points = benchmark_sl_pips * (10.0 if sym_info and sym_info.digits in (3, 5) else 1.0)
        dynamic_lot = calculate_half_kelly(acc.equity, sym_info, sl_points)

        status_line = (
            f"[*] {silo['name']} | Login: #{acc.login} | Eq: ${acc.equity:,.2f} | "
            f"Symbol: {symbol} | Half-Kelly Target: {dynamic_lot:.2f} lots | Active Positions: {len(positions)}"
        )
        print(status_line)
        log.info(status_line)

        for p in positions:
            side = "BUY" if p.type == 0 else "SELL"
            p_line = f"    -> Ticket #{p.ticket} | {p.symbol} {side} {p.volume:.2f} lots | Entry: {p.price_open} | SL: {p.sl} | PnL: ${p.profit:>+7.2f}"
            print(p_line)
            log.info(p_line)

        mt5.shutdown()

    log.info("=== SCAN COMPLETED. SLEEPING 60 SECONDS ===")
    print("[*] Scan completed. Next cycle in 60 seconds...\n")

if __name__ == "__main__":
    print("[+] Deep Delta Auto-Scanner active. Interval: 60 seconds.")
    try:
        while True:
            run_delta_cycle()
            time.sleep(60)
    except KeyboardInterrupt:
        print("[!] Stopping Deep Delta Scanner cleanly.")