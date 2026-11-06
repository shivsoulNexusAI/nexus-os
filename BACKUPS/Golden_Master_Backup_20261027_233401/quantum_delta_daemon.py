"""
QUANTUM DELTA DAEMON // INSTITUTIONAL TELEMETRY, KRONOS GATING, & AUTONOMOUS MT5 EXECUTION
"""
import sys
import os

# 1. Enforce UTF-8 streams globally on Windows consoles (prevents cp1251 charmap crashes on emojis)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import time
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
import MetaTrader5 as mt5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8883861115:AAFAUqBcKSYjrIgo-Spoc5WuqSONeITx6Yw").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5279761713").strip()
SHADOW_PATH = os.path.join(BASE_DIR, "shadow_portfolio.json")

# Environmental Configuration & Risk Parameters
env_symbols = os.getenv("RADAR_SYMBOLS", "XAUUSD,BTCUSD,ETHUSD,EURUSD,GBPUSD,US30")
SYMBOLS = [s.strip().upper() for s in env_symbols.split(",") if s.strip()]
EXECUTION_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "0.72"))  # 72% - 75% Baseline Threshold
MAX_PORTFOLIO_SLOTS = 6
DRAWDOWN_CIRCUIT_BREAKER = 950.00
COOLDOWN_ALERT_SECONDS = 300       # 5-min cooldown for single-card telegram broadcast
COOLDOWN_EXECUTION_SECONDS = 600   # 10-min cooldown per symbol for auto-order dispatch

# Module Injections
try:
    from kronos_regime_governor import governor
except ImportError:
    governor = None

try:
    from confluence_engine import confluence_engine
except ImportError:
    confluence_engine = None

try:
    from risk_allocator import kelly_engine
except ImportError:
    kelly_engine = None

# In-Memory State Cache
alert_history = {}
execution_history = {}


def send_telegram_html(message: str) -> bool:
    """Dispatches HTML message to Telegram Alert Bot."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=8)
        return res.status_code == 200
    except Exception as e:
        print(f"[!] Telegram dispatch failure: {e}")
        return False


def get_market_data(symbol: str, timeframe=mt5.TIMEFRAME_M1, n_bars: int = 100) -> pd.DataFrame:
    """Fetches M1 rates directly from MT5 API."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df


def execute_mt5_trade(symbol: str, direction: str, entry_price: float, sl_price: float, tp_price: float, lots: float, edge: float) -> bool:
    """Autonomous MT5 Order Execution enforcing ORDER_FILLING_FOK and Circuit Breaker."""
    if not mt5.initialize():
        return False

    acc = mt5.account_info()
    if not acc:
        print("[!] Execution vetoed: Failed to retrieve account info.")
        return False

    # 1. Hard Drawdown Circuit Breaker Gate
    if acc.equity < DRAWDOWN_CIRCUIT_BREAKER:
        print(f"[!] EMERGENCY CIRCUIT BREAKER: Equity ${acc.equity:,.2f} is below floor ${DRAWDOWN_CIRCUIT_BREAKER:,.2f}.")
        return False

    # 2. Portfolio Slot & Open Position Limit Gate
    positions = mt5.positions_get()
    open_count = len(positions) if positions else 0
    if open_count >= MAX_PORTFOLIO_SLOTS:
        print(f"[!] Auto-trade vetoed: Portfolio capacity full ({open_count}/{MAX_PORTFOLIO_SLOTS}).")
        return False

    # Prevent concurrent duplicate trades on same symbol
    if positions:
        for p in positions:
            if p.symbol == symbol:
                print(f"[!] Auto-trade vetoed: Position already open for {symbol}.")
                return False

    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return False

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid
    digits = sym_info.digits
    lot_step = sym_info.volume_step if sym_info.volume_step else 0.01

    # Clamp lot size between volume min/max, rounded to volume step
    lots = max(sym_info.volume_min, min(lots, sym_info.volume_max))
    lots = round(round(lots / lot_step) * lot_step, 2)
    lots = min(lots, 0.01)  # Enforce micro-lot safety ceiling on trial phase

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": float(round(price, digits)),
        "sl": float(round(sl_price, digits)) if sl_price > 0 else 0.0,
        "tp": float(round(tp_price, digits)) if tp_price > 0 else 0.0,
        "deviation": 20,
        "magic": 999369,
        "comment": f"Nexus Auto {edge*100:.0f}%",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK  # Mode 1: Fill Or Kill enforced
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        ticket = result.order
        side_icon = "🟢" if direction == "BUY" else "🔴"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 ORDER EXECUTED: {symbol} {direction} {lots} Lots @ {result.price:.5f} (Ticket #{ticket})")

        confirm_msg = (
            f"⚡ <b>AUTONOMOUS MT5 TRADE EXECUTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{side_icon} <b>{symbol} {direction}</b> | <code>{lots:.2f} Lots</code>\n"
            f"• <b>Edge Score</b>: <code>{edge*100:.1f}%</code> (Crossed {EXECUTION_THRESHOLD*100:.0f}% Threshold)\n"
            f"• <b>Ticket</b>: <code>#{ticket}</code>\n"
            f"• <b>Fill Price</b>: <code>{result.price:.5f}</code>\n"
            f"• <b>SL</b>: <code>{sl_price:.5f}</code> | <b>TP</b>: <code>{tp_price:.5f}</code>\n"
            f"• <b>Filling Mode</b>: <code>ORDER_FILLING_FOK</code>\n"
            f"• <b>Account</b>: <code>#{acc.login}</code> (${acc.equity:,.2f})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 <i>Nexus Autonomous Execution Engine</i>"
        )
        send_telegram_html(confirm_msg)
        return True
    else:
        err_code = result.retcode if result else mt5.last_error()
        err_comment = result.comment if result else "No response"
        print(f"[!] MT5 Order execution rejected: Code {err_code} ({err_comment})")
        return False


def run_cycle():
    """Runs single 60s ranking, gating audit, and execution cycle."""
    if not mt5.initialize():
        print("[!] MT5 not initialized for scanner cycle.")
        return

    now_ts = time.time()
    candidates = []

    for sym in SYMBOLS:
        tick = mt5.symbol_info_tick(sym)
        sym_info = mt5.symbol_info(sym)
        if not tick or not sym_info:
            continue

        df = get_market_data(sym, mt5.TIMEFRAME_M1, 100)
        if df is None or len(df) < 50:
            continue

        spread_points = tick.ask - tick.bid
        close_curr = df['close'].iloc[-1]
        close_prev = df['close'].iloc[-10]
        delta_pct = ((close_curr - close_prev) / close_prev) * 100.0

        direction = "BUY" if delta_pct >= 0 else "SELL"

        # 1. Governor Evaluation Gate
        if governor is not None:
            passed_gov, regime, score, reason = governor.evaluate_setup(sym, direction, df, current_spread=spread_points)
            feats = governor.extract_features(df) if hasattr(governor, "extract_features") else {"vpin_toxicity": 0.20, "efficiency_ratio": 0.50}
        else:
            passed_gov, regime, score, reason = True, "CLEAN_TREND", 0.82, "Governor bypass"
            feats = {"vpin_toxicity": 0.20, "efficiency_ratio": 0.50}

        # 2. Confluence Engine Gate
        if confluence_engine is not None:
            passed_conf, conf_score, conf_status, macro_data = confluence_engine.verify_alignment(sym, direction)
            combined_edge = score * (0.60 + 0.40 * conf_score) if passed_conf else score * 0.50
            h1_b = macro_data.get('H1', {}).get('bias', 'N/A')
            h4_b = macro_data.get('H4', {}).get('bias', 'N/A')
        else:
            passed_conf = True
            conf_score = 1.00
            conf_status = "Bypass"
            combined_edge = score
            h1_b, h4_b = "N/A", "N/A"

        # 3. Dynamic Stop Loss & Take Profit
        atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        if np.isnan(atr) or atr == 0:
            atr = sym_info.point * 150

        entry_price = tick.ask if direction == "BUY" else tick.bid
        sl_price = entry_price - (1.5 * atr) if direction == "BUY" else entry_price + (1.5 * atr)
        tp_price = entry_price + (3.0 * atr) if direction == "BUY" else entry_price - (3.0 * atr)
        lots = 0.01

        candidates.append({
            "symbol": sym,
            "direction": direction,
            "edge": combined_edge,
            "delta_pct": delta_pct,
            "regime": regime,
            "h1": h1_b,
            "h4": h4_b,
            "entry": entry_price,
            "sl": sl_price,
            "tp": tp_price,
            "lots": lots,
            "passed_gov": passed_gov,
            "passed_conf": passed_conf,
            "gov_reason": reason,
            "conf_status": conf_status,
            "feats": feats
        })

    if not candidates:
        return

    # Rank symbols strictly by Edge Score descending
    candidates.sort(key=lambda x: x["edge"], reverse=True)

    # Dispatch autonomous MT5 order if all three gates pass
    for c in candidates:
        if c["edge"] >= EXECUTION_THRESHOLD and c["passed_gov"] and c["passed_conf"]:
            last_exec = execution_history.get(c["symbol"])
            if last_exec and (now_ts - last_exec) < COOLDOWN_EXECUTION_SECONDS:
                continue

            success = execute_mt5_trade(
                symbol=c["symbol"],
                direction=c["direction"],
                entry_price=c["entry"],
                sl_price=c["sl"],
                tp_price=c["tp"],
                lots=c["lots"],
                edge=c["edge"]
            )
            if success:
                execution_history[c["symbol"]] = now_ts
                break  # Max 1 automated order dispatch per scanner cycle

    # Build State-Synchronized Kronos Radar Telegram Broadcast
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "⚡ <b>KRONOS RADAR // 60S MOMENTUM RANKING</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏱️ <code>{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</code> | Threshold: <code>{EXECUTION_THRESHOLD*100:.0f}%+ Auto-Fire</code>\n"
    ]

    for idx, c in enumerate(candidates):
        medal = medals[idx] if idx < len(medals) else f" {idx+1}."
        side_icon = "🟢" if c["direction"] == "BUY" else "🔴"

        # Governor-Aware Radar Badges
        if c["edge"] >= EXECUTION_THRESHOLD:
            if c.get("passed_gov") and c.get("passed_conf"):
                fire_badge = " [🚀 FIRE]"
            elif not c.get("passed_gov"):
                fire_badge = " [🛡️ GOV VETO]"
            else:
                fire_badge = " [⚠️ CONF VETO]"
        else:
            fire_badge = ""

        lines.append(
            f"<b>{medal} {c['symbol']}</b>: {side_icon} {c['direction']} | <b>{c['edge']*100:.1f}% Edge</b>{fire_badge}\n"
            f"   └ <i>{c['regime']}</i> (Δ {c['delta_pct']:+.2f}%) | H1: <code>{c['h1']}</code>"
        )

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔒 <i>Autonomous Execution: Active for Edge ≥ {EXECUTION_THRESHOLD*100:.0f}%</i>")
    radar_msg = "\n".join(lines)

    send_telegram_html(radar_msg)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Dispatched Kronos 60s Radar. Top: {candidates[0]['symbol']} ({candidates[0]['edge']*100:.1f}%)")


def main():
    print("🚀 Quantum Delta Daemon [60s Ranking & Auto-Execution Engine] Online.")
    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"[!] Scanner cycle exception: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()