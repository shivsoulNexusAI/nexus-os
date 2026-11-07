"""
QUANTUM DELTA DAEMON (v3.1 Institutional Production)
Multi-Asset Microstructure:
  - Opening Range Breakout (ORB) & Session Killzone Engine (UTC)
  - M5 Fair Value Gap (FVG) Imbalance Detection
  - Market Structure Shift (MSS) Swing Pivot Confluence
  - Dynamic Fractional Kelly Risk Kernel Sizing
  - Non-Blocking Asynchronous Trio Bot Telemetry
  - Strict GC Thresholds for 1GB VPS Stability
"""
import os
import gc
import sys
import time
import logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

sys.path.append(r"C:\Quant-Nexus-Eng")
from nexus_risk_kernel import risk_kernel
from nexus_telegram import send_alert

LOG_PATH = r"C:\Quant-Nexus-Eng\quantum_delta_daemon.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("QuantumDeltaDaemon")

MT5_PATH = r"C:\MT5_HFT_278041671\terminal64.exe"
SYMBOLS = ["XAUUSD247", "EURUSD", "GBPUSD", "BTCUSD"]
MAGIC_DELTA = 888001
LOOP_CADENCE_SEC = 10

class InstitutionalKillzoneEngine:
    """
    Manages institutional session boundaries and opening range references:
      - Asian Range:        00:00 - 06:00 UTC
      - London Open (LO):   07:00 - 10:00 UTC (Initial 15m ORB: 07:00 - 07:15 UTC)
      - New York AM (NYAM): 12:30 - 15:30 UTC (Initial 15m ORB: 12:30 - 12:45 UTC)
      - Synthetic 24/7 (XAUUSD247/BTCUSD): Allowed continuously, tagged with active session.
    """
    @staticmethod
    def get_session_context(symbol: str) -> dict:
        now_utc = datetime.now(timezone.utc)
        curr_min = now_utc.hour * 60 + now_utc.minute

        # Session intervals in UTC minutes
        sessions = [
            {"name": "LONDON_OPEN", "start": 7 * 60, "end": 10 * 60, "orb_window": (7 * 60, 7 * 60 + 15)},
            {"name": "NEW_YORK_AM", "start": 12 * 60 + 30, "end": 15 * 60 + 30, "orb_window": (12 * 60 + 30, 12 * 60 + 45)},
            {"name": "ASIAN_RANGE", "start": 0, "end": 6 * 60, "orb_window": (0, 15)}
        ]

        active_kz = None
        for s in sessions:
            if s["start"] <= curr_min < s["end"]:
                active_kz = s
                break

        is_synthetic = any(k in symbol.upper() for k in ["247", "BTC"])

        if active_kz is None:
            return {
                "in_killzone": is_synthetic,
                "session": "OFF_SESSION" if not is_synthetic else "SYNTHETIC_CONTINUOUS",
                "is_orb_expansion": False,
                "active_kz": active_kz
            }

        # Check if currently inside the initial 15-minute Opening Range window
        is_orb_forming = active_kz["orb_window"][0] <= curr_min < active_kz["orb_window"][1]

        return {
            "in_killzone": True,
            "session": active_kz["name"],
            "is_orb_forming": is_orb_forming,
            "active_kz": active_kz
        }

    @staticmethod
    def audit_orb_levels(df: pd.DataFrame, orb_window_bars: int = 3) -> dict:
        """
        Calculates the Opening Range high and low boundaries from the initial M5 candles of the session.
        """
        if len(df) < orb_window_bars + 5:
            return {"orb_high": 0.0, "orb_low": 0.0, "breakout": "NONE"}

        orb_bars = df.iloc[-(orb_window_bars + 5):-5]
        orb_high = orb_bars["high"].max()
        orb_low = orb_bars["low"].min()
        cur_price = df.iloc[-1]["close"]

        if cur_price > orb_high:
            breakout = "ORB_BULLISH_EXPANSION"
        elif cur_price < orb_low:
            breakout = "ORB_BEARISH_EXPANSION"
        else:
            breakout = "ORB_INSIDE_CONSOLIDATION"

        return {
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout": breakout
        }


class SmartMoneyStructureEngine:
    @staticmethod
    def audit_fvg(df: pd.DataFrame) -> dict:
        """Evaluates 3-candle Fair Value Gap (FVG) on M5."""
        if len(df) < 3:
            return {"type": "NONE", "gap_size": 0.0, "top": 0.0, "bottom": 0.0}

        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]

        # Bullish FVG: Candle 1 High < Candle 3 Low
        if c3["low"] > c1["high"]:
            gap = c3["low"] - c1["high"]
            return {"type": "BULLISH_FVG", "gap_size": gap, "bottom": c1["high"], "top": c3["low"]}

        # Bearish FVG: Candle 1 Low > Candle 3 High
        if c3["high"] < c1["low"]:
            gap = c1["low"] - c3["high"]
            return {"type": "BEARISH_FVG", "gap_size": gap, "top": c1["low"], "bottom": c3["high"]}

        return {"type": "BALANCED", "gap_size": 0.0, "top": 0.0, "bottom": 0.0}

    @staticmethod
    def audit_mss(df: pd.DataFrame) -> dict:
        """Detects Market Structure Shift (MSS) using 15-period swing pivots."""
        if len(df) < 15:
            return {"shift": "NONE", "pivot_price": 0.0}

        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        recent_swing_high = np.max(highs[-15:-3])
        recent_swing_low = np.min(lows[-15:-3])
        current_close = closes[-1]

        if current_close > recent_swing_high:
            return {"shift": "BULLISH_MSS", "pivot_price": recent_swing_high}
        elif current_close < recent_swing_low:
            return {"shift": "BEARISH_MSS", "pivot_price": recent_swing_low}

        return {"shift": "CONSOLIDATION", "pivot_price": 0.0}


def evaluate_asset_cycle():
    clear, reason, metrics = risk_kernel.audit_governance()
    if not clear:
        logger.warning(f"[RISK-VETO] Governance lockout active: {reason}")
        return

    for sym in SYMBOLS:
        kz = InstitutionalKillzoneEngine.get_session_context(sym)
        
        # Killzone Filter Gate: Bypass off-hours for standard forex pairs
        if not kz["in_killzone"]:
            continue

        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 15:
            continue

        df = pd.DataFrame(rates)
        fvg = SmartMoneyStructureEngine.audit_fvg(df)
        mss = SmartMoneyStructureEngine.audit_mss(df)
        orb = InstitutionalKillzoneEngine.audit_orb_levels(df)

        tick = mt5.symbol_info_tick(sym)
        spread = (tick.ask - tick.bid) if tick else 0.0
        cur_price = df.iloc[-1]["close"]

        # Triple Institutional Confluence:
        # 1. Active Session / ORB Expansion
        # 2. M5 FVG Imbalance
        # 3. M5 Market Structure Shift (MSS)
        
        bullish_confluence = (
            fvg["type"] == "BULLISH_FVG" and 
            mss["shift"] == "BULLISH_MSS" and 
            orb["breakout"] in ["ORB_BULLISH_EXPANSION", "ORB_INSIDE_CONSOLIDATION"]
        )

        bearish_confluence = (
            fvg["type"] == "BEARISH_FVG" and 
            mss["shift"] == "BEARISH_MSS" and 
            orb["breakout"] in ["ORB_BEARISH_EXPANSION", "ORB_INSIDE_CONSOLIDATION"]
        )

        if bullish_confluence:
            lots = risk_kernel.compute_position_size(sym, stop_loss_points=250, edge=0.64)
            logger.info(f"🎯 [ORB+SMC CONFLUENCE] {sym} BULLISH MSS + FVG | KZ: {kz['session']} | Price: {cur_price:.3f} | Sizing: {lots} Lots")
            send_alert(
                "quant_alert_bot",
                f"🚀 <b>[ORB+SMC ALPHA TRIGGER]</b> <code>{sym}</code>\n"
                f"• Session: <b>{kz['session']}</b>\n"
                f"• Setup: <b>BULLISH MSS + FVG + {orb['breakout']}</b>\n"
                f"• Close: <code>{cur_price:.3f}</code> | Spread: <code>${spread:.2f}</code>\n"
                f"• Dynamic Kelly Sizing: <code>{lots:.2f} Lots</code>"
            )

        elif bearish_confluence:
            lots = risk_kernel.compute_position_size(sym, stop_loss_points=250, edge=0.64)
            logger.info(f"🎯 [ORB+SMC CONFLUENCE] {sym} BEARISH MSS + FVG | KZ: {kz['session']} | Price: {cur_price:.3f} | Sizing: {lots} Lots")
            send_alert(
                "quant_alert_bot",
                f"🔻 <b>[ORB+SMC ALPHA TRIGGER]</b> <code>{sym}</code>\n"
                f"• Session: <b>{kz['session']}</b>\n"
                f"• Setup: <b>BEARISH MSS + FVG + {orb['breakout']}</b>\n"
                f"• Close: <code>{cur_price:.3f}</code> | Spread: <code>${spread:.2f}</code>\n"
                f"• Dynamic Kelly Sizing: <code>{lots:.2f} Lots</code>"
            )


def main():
    logger.info("Initializing Quantum Delta SMC + ORB Daemon...")
    if not mt5.initialize(path=MT5_PATH):
        logger.error("Failed to connect to MT5 terminal.")
        return

    logger.info("Connected to MT5. Starting continuous ORB/SMC/FVG pipeline...")
    gc.set_threshold(700, 10, 5)

    try:
        while True:
            evaluate_asset_cycle()
            gc.collect()  # Enforce tight RAM ceiling for 1GB VPS
            time.sleep(LOOP_CADENCE_SEC)
    except KeyboardInterrupt:
        logger.info("Daemon halted by operator.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()