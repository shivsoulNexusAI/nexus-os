# -*- coding: utf-8 -*-
"""
SHIVSOUL QUANTITATIVE DESK - LIVE FORWARD SHADOW TRACKER
Evaluates live market conditions, logs virtual trades, tracks real-time ticks,
and simulates institutional execution without placing financial capital at risk.
"""

import os
import time
import json
import uuid
from datetime import datetime, timezone
import pandas as pd
import MetaTrader5 as mt5

# Import Regime Governor if available
try:
    from regime_governor import RegimeGovernor
    governor = RegimeGovernor()
except Exception as e:
    governor = None
    print(f"[-] Shadow Tracker running without ML Governor: {e}")

PORTFOLIO_FILE = "shadow_portfolio.json"
JOURNAL_FILE = "shadow_journal.csv"
CONFIG_FILE = "threshold_config.json"
SCAN_INTERVAL_SECONDS = 30  # Scan M5 candles every 30s
TICK_POLL_INTERVAL = 1      # Poll virtual orders every 1s

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "sectors" in data:
                    flat = {}
                    for sec in data["sectors"].values():
                        if sec.get("enabled", True):
                            for sym, a_cfg in sec.get("assets", {}).items():
                                flat[sym] = a_cfg
                    return flat
                return data
        except Exception:
            pass
    return {
        "EURUSD": {"min_edge": 75, "risk_percent": 1.0},
        "GBPUSD": {"min_edge": 75, "risk_percent": 1.0},
        "USDJPY": {"min_edge": 72, "risk_percent": 0.75},
        "XAUUSD": {"min_edge": 80, "risk_percent": 0.5},
        "BTCUSD": {"min_edge": 82, "risk_percent": 0.5}
    }

def load_shadow_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": 10000.0, "equity": 10000.0, "positions": {}}

def save_shadow_portfolio(data):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def log_trade_to_journal(trade_record: dict):
    file_exists = os.path.exists(JOURNAL_FILE)
    df = pd.DataFrame([trade_record])
    df.to_csv(JOURNAL_FILE, mode="a", index=False, header=not file_exists)

def evaluate_setup(symbol: str, cfg: dict):
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
    if rates is None or len(rates) < 20:
        return None

    df = pd.DataFrame(rates)
    cur = df["close"].iloc[-1]
    high_max = df["high"].iloc[-15:].max()
    low_min = df["low"].iloc[-15:].min()
    rng = high_max - low_min if high_max > low_min else 0.0001

    pos_in_range = (cur - low_min) / rng
    if pos_in_range < 0.25:
        direction = "BUY"
        edge = min(92, int(60 + (1 - pos_in_range) * 30))
        sl = low_min - (rng * 0.1)
        tp = cur + (abs(cur - sl) * 2.2)
    elif pos_in_range > 0.75:
        direction = "SELL"
        edge = min(92, int(60 + pos_in_range * 30))
        sl = high_max + (rng * 0.1)
        tp = cur - (abs(sl - cur) * 2.2)
    else:
        return None

    if edge < cfg.get("min_edge", 75):
        return None

    sl_dist = abs(cur - sl)
    if sl_dist <= 0:
        return None

    # Regime Governor Assessment
    ml_regime = "NEUTRAL"
    ml_verdict = "APPROVED"
    ml_mult = 1.0
    if governor:
        try:
            eval_res = governor.evaluate(symbol)
            ml_regime = eval_res.get("regime", "UNKNOWN")
            ml_verdict = eval_res.get("verdict", "APPROVED")
            ml_mult = eval_res.get("risk_multiplier", 1.0)
        except Exception:
            pass

    return {
        "symbol": symbol,
        "direction": direction,
        "edge": edge,
        "raw_sl": sl,
        "raw_tp": tp,
        "sl_dist": sl_dist,
        "risk_percent": cfg.get("risk_percent", 1.0) * ml_mult,
        "ml_regime": ml_regime,
        "ml_verdict": ml_verdict
    }

def update_open_shadow_positions(portfolio: dict):
    active_keys = list(portfolio["positions"].keys())
    closed_any = False

    for ticket in active_keys:
        pos = portfolio["positions"][ticket]
        sym = pos["symbol"]
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            continue

        bid = tick.bid
        ask = tick.ask
        direction = pos["direction"]
        entry_price = pos["entry_price"]
        sl = pos["sl"]
        tp = pos["tp"]
        sl_dist = pos["sl_dist"]
        be_active = pos.get("be_active", False)

        closed = False
        outcome = ""
        exit_price = 0.0

        if direction == "BUY":
            # 1. Breakeven Trailing (+1.0R reached)
            if not be_active and bid >= (entry_price + sl_dist):
                pos["sl"] = entry_price
                pos["be_active"] = True
                print(f"[SHADOW TRAIL] #{ticket[:8]} {sym} BUY moved to BREAKEVEN @ {entry_price:.5f}")

            # 2. Check Exits (Sell trades execute at Ask, Buy trades exit at Bid)
            if bid <= sl:
                exit_price = sl
                outcome = "BREAKEVEN" if pos.get("be_active", False) and exit_price == entry_price else "LOSS"
                closed = True
            elif bid >= tp:
                exit_price = tp
                outcome = "WIN"
                closed = True

        elif direction == "SELL":
            # 1. Breakeven Trailing (+1.0R reached)
            if not be_active and ask <= (entry_price - sl_dist):
                pos["sl"] = entry_price
                pos["be_active"] = True
                print(f"[SHADOW TRAIL] #{ticket[:8]} {sym} SELL moved to BREAKEVEN @ {entry_price:.5f}")

            # 2. Check Exits (Sell exits at Ask)
            if ask >= sl:
                exit_price = sl
                outcome = "BREAKEVEN" if pos.get("be_active", False) and exit_price == entry_price else "LOSS"
                closed = True
            elif ask <= tp:
                exit_price = tp
                outcome = "WIN"
                closed = True

        if closed:
            r_multiple = (exit_price - entry_price) / sl_dist if direction == "BUY" else (entry_price - exit_price) / sl_dist
            dollar_pnl = r_multiple * pos["dollar_risk"]
            portfolio["balance"] += dollar_pnl
            portfolio["equity"] = portfolio["balance"]

            closed_record = {
                "ticket": ticket,
                "symbol": sym,
                "direction": direction,
                "edge": pos["edge"],
                "ml_regime": pos["ml_regime"],
                "entry_time": pos["entry_time"],
                "exit_time": datetime.now(timezone.utc).isoformat(),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "outcome": outcome,
                "r_multiple": round(r_multiple, 2),
                "dollar_pnl": round(dollar_pnl, 2),
                "final_balance": round(portfolio["balance"], 2)
            }
            log_trade_to_journal(closed_record)
            del portfolio["positions"][ticket]
            closed_any = True
            print(f"[SHADOW CLOSE] {sym} {direction} -> {outcome} ({r_multiple:+.2f}R | ${dollar_pnl:+.2f}) | New Balance: ${portfolio['balance']:,.2f}")

    if closed_any:
        save_shadow_portfolio(portfolio)

def run_shadow_scanner():
    if not mt5.initialize():
        print("[-] Error: MetaTrader 5 offline. Cannot start Shadow Tracker.")
        return

    print("=======================================================")
    print("      NEXUS SHADOW TRACKER - LIVE FORWARD LAB         ")
    print("=======================================================")
    
    portfolio = load_shadow_portfolio()
    cfg_symbols = load_config()
    print(f"[*] Shadow Portfolio Loaded. Balance: ${portfolio['balance']:,.2f} | Open Virtual Tickets: {len(portfolio['positions'])}")

    last_scan = 0

    try:
        while True:
            now = time.time()
            
            # 1. Update Open Virtual Positions on Every Loop Tick
            update_open_shadow_positions(portfolio)

            # 2. Scan M5 Setups on Interval
            if now - last_scan > SCAN_INTERVAL_SECONDS:
                last_scan = now
                cfg_symbols = load_config()

                for sym, cfg in cfg_symbols.items():
                    # Check if already in trade on this symbol
                    already_trading = any(p["symbol"] == sym for p in portfolio["positions"].values())
                    if already_trading:
                        continue

                    setup = evaluate_setup(sym, cfg)
                    if not setup:
                        continue

                    if setup["ml_verdict"] == "VETO":
                        # Record vetoed shadow instance to quantify prevented losses
                        log_trade_to_journal({
                            "ticket": f"VETO-{uuid.uuid4().hex[:6]}",
                            "symbol": sym,
                            "direction": setup["direction"],
                            "edge": setup["edge"],
                            "ml_regime": setup["ml_regime"],
                            "entry_time": datetime.now(timezone.utc).isoformat(),
                            "exit_time": datetime.now(timezone.utc).isoformat(),
                            "entry_price": 0.0,
                            "exit_price": 0.0,
                            "outcome": "ML_VETO_BLOCKED",
                            "r_multiple": 0.0,
                            "dollar_pnl": 0.0,
                            "final_balance": portfolio["balance"]
                        })
                        continue

                    # Execute Virtual Order at Real Market Ticks
                    tick = mt5.symbol_info_tick(sym)
                    if not tick:
                        continue

                    entry_price = tick.ask if setup["direction"] == "BUY" else tick.bid
                    ticket_id = f"SHADOW-{uuid.uuid4().hex[:8].upper()}"
                    dollar_risk = portfolio["balance"] * (setup["risk_percent"] / 100.0)

                    portfolio["positions"][ticket_id] = {
                        "symbol": sym,
                        "direction": setup["direction"],
                        "edge": setup["edge"],
                        "entry_time": datetime.now(timezone.utc).isoformat(),
                        "entry_price": entry_price,
                        "sl": setup["raw_sl"],
                        "tp": setup["raw_tp"],
                        "sl_dist": setup["sl_dist"],
                        "dollar_risk": dollar_risk,
                        "ml_regime": setup["ml_regime"],
                        "be_active": False
                    }
                    save_shadow_portfolio(portfolio)
                    print(f"\n[SHADOW ENTRY] #{ticket_id} {sym} {setup['direction']} @ {entry_price:.5f} (Edge: {setup['edge']}% | Regime: {setup['ml_regime']} | Risk: ${dollar_risk:.2f})")

            time.sleep(TICK_POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n[*] Stopping Shadow Tracker. Virtual portfolio state saved.")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    run_shadow_scanner()