# =====================================================================
# SHIVSOUL NEXUS v7.0 // EMERGENCY MULTI-SLEEVE POSITION FLATTENER
# =====================================================================
import sys
import json
from datetime import datetime, timezone
import MetaTrader5 as mt5
from nexus_ship_core import SLEEVES


def resolve_filling_mode(symbol_info) -> int:
    modes = int(getattr(symbol_info, "filling_mode", 0))
    if modes & 2:  # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    if modes & 1:  # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def flatten_all_sleeves() -> dict:
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "closed": [],
        "errors": [],
        "sleeves_checked": 0,
    }

    for sleeve_name, cfg in SLEEVES.items():
        summary["sleeves_checked"] += 1
        ok = mt5.initialize(
            path=cfg["path"],
            login=cfg["login"],
            password=cfg["password"],
            server=cfg["server"],
        )
        if not ok:
            code, desc = mt5.last_error()
            summary["errors"].append(f"{sleeve_name}: MT5 init failed ({code}: {desc})")
            continue

        try:
            positions = mt5.positions_get()
            if not positions:
                continue

            for pos in positions:
                sym = pos.symbol
                mt5.symbol_select(sym, True)
                tick = mt5.symbol_info_tick(sym)
                sym_info = mt5.symbol_info(sym)

                if not tick or not sym_info:
                    summary["errors"].append(f"{sleeve_name} #{pos.ticket} ({sym}): missing tick/symbol info")
                    continue

                is_buy = pos.type == mt5.POSITION_TYPE_BUY
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                close_price = tick.bid if is_buy else tick.ask

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": sym,
                    "volume": float(pos.volume),
                    "type": close_type,
                    "position": int(pos.ticket),
                    "price": float(close_price),
                    "deviation": 50,
                    "magic": int(pos.magic),
                    "comment": "NEXUS_EMERGENCY_CLOSE_ALL",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": resolve_filling_mode(sym_info),
                }

                res = mt5.order_send(request)
                if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                    summary["closed"].append({
                        "sleeve": sleeve_name,
                        "ticket": int(pos.ticket),
                        "symbol": sym,
                        "volume": float(pos.volume),
                        "close_price": float(res.price or close_price),
                        "profit": float(pos.profit),
                    })
                else:
                    rc = res.retcode if res is not None else "None"
                    cmt = res.comment if res is not None else str(mt5.last_error())
                    summary["errors"].append(
                        f"{sleeve_name} #{pos.ticket} ({sym}): retcode={rc} ({cmt})"
                    )
        finally:
            mt5.shutdown()

    return summary


if __name__ == "__main__":
    result = flatten_all_sleeves()
    print(json.dumps(result))
    sys.exit(0 if not result["errors"] else 1)
