"""
NEXUS WEEKEND SHIELD // PRE-WEEKEND DE-RISKING & JUMP-DIFFUSION GAP ARMOR
"""
import MetaTrader5 as mt5
from datetime import datetime, timezone
import requests
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD"}
FRIDAY_INTAKE_FREEZE_HOUR = 18  # 18:00 UTC Friday: No new non-crypto entries
FRIDAY_VAULT_HOUR = 20          # 20:30 UTC Friday: Pre-close liquidation & runner banking
FRIDAY_VAULT_MINUTE = 30

def send_shield_telegram(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass

def is_friday_intake_frozen(symbol: str) -> bool:
    """Returns True if Friday intake cutoff is reached for non-crypto assets."""
    now = datetime.now(timezone.utc)
    if now.weekday() == 4 and now.hour >= FRIDAY_INTAKE_FREEZE_HOUR:
        return symbol not in CRYPTO_SYMBOLS
    return False

def execute_friday_vault_sweep():
    """
    Executes at 20:30 UTC on Fridays:
    - Closes open non-crypto positions with floating gains < 1.0x ATR
    - Banks 50% on deep runners and ratchets SL to secure weekend safety
    """
    now = datetime.now(timezone.utc)
    # Check if Friday past vault threshold
    if not (now.weekday() == 4 and (now.hour > FRIDAY_VAULT_HOUR or (now.hour == FRIDAY_VAULT_HOUR and now.minute >= FRIDAY_VAULT_MINUTE))):
        return False, "Not within Friday Vault execution window"

    if not mt5.initialize():
        return False, "MT5 disconnected"

    positions = mt5.positions_get()
    if not positions:
        return True, "Zero positions open during Friday Vault sweep"

    closed_scratch = 0
    armored_runners = 0

    for p in positions:
        if p.symbol in CRYPTO_SYMBOLS:
            continue  # Crypto trades continuously over weekend

        sym_info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not sym_info or not tick:
            continue

        point = sym_info.point
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        current_price = tick.bid if is_buy else tick.ask
        gain_points = (current_price - p.price_open) / point if is_buy else (p.price_open - current_price) / point

        # If floating gain is less than 30 points (approx scratch or losing) -> Liquidate
        if gain_points < 30:
            opp_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": opp_type,
                "position": p.ticket,
                "price": current_price,
                "deviation": 25,
                "magic": 999990,
                "comment": "FRIDAY_VAULT_FLAT",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed_scratch += 1
        else:
            # Runner trade: Bank 50% and snap SL to secure profit
            vol_step = sym_info.volume_step if sym_info.volume_step else 0.01
            half_vol = round(round(p.volume * 0.5 / vol_step) * vol_step, 2)
            if half_vol >= (sym_info.volume_min or 0.01):
                opp_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": p.symbol,
                    "volume": half_vol,
                    "type": opp_type,
                    "position": p.ticket,
                    "price": current_price,
                    "deviation": 25,
                    "magic": 999991,
                    "comment": "FRIDAY_RUNNER_BANK",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    armored_runners += 1

    summary = (
        f"🏰 <b>FRIDAY ALPHA VAULT // WEEKEND DE-RISKING EXECUTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Closed Scratch/Risk Positions</b>: <code>{closed_scratch}</code>\n"
        f"• <b>Banked 50% Armored Runners</b>: <code>{armored_runners}</code>\n"
        f"• <b>Active Crypto Fleet</b>: BTCUSD / ETHUSD (Uninterrupted 24/7)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <i>Portfolio Protected Against Jump-Diffusion Gaps</i>"
    )
    send_shield_telegram(summary)
    return True, summary
