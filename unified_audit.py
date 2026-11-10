# -*- coding: utf-8 -*-
import MetaTrader5 as mt5

# Target paths aligned to running instances
targets = [
    ("T1 Silver Bullet", r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe", False),
    ("T2 Majors Grid",   r"C:\Users\AdmVps\Documents\MetaTrader 5\terminal64.exe", False),
    ("T2 Pending (Dir)", r"C:\MT5_Pending_278041169\terminal64.exe", False),
    ("T3 Gold HFT",      r"C:\MT5_HFT_278041671\terminal64.exe", True),
]

print("=" * 90)
print("             NEXUS 3-SILO TRUE RUNTIME TOPOLOGY")
print("=" * 90)

connected_accounts = set()

for label, exe_path, is_portable in targets:
    ok = mt5.initialize(path=exe_path, portable=is_portable)
    if not ok:
        # Fallback to alternate mode
        ok = mt5.initialize(path=exe_path, portable=not is_portable)

    if ok:
        acc = mt5.account_info()
        term = mt5.terminal_info()
        login = getattr(acc, "login", None)
        if login and login not in connected_accounts:
            connected_accounts.add(login)
            equity = getattr(acc, "equity", 0.0)
            algo = "ALGO ON [OK]" if getattr(term, "trade_allowed", False) else "ALGO OFF [LOCKED]"
            pos = len(mt5.positions_get() or [])
            pending = len(mt5.orders_get() or [])
            print(f"[+] {label:<18} : Account #{login:<10} | Equity: ${equity:>8.2f} | {algo:<16} | Pos: {pos} | Pending: {pending}")
            
            # Print T2 details if it has orders
            if login == 278041169:
                for o in mt5.orders_get() or []:
                    t_name = {mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP", mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP", mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT", mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT"}.get(o.type, str(o.type))
                    print(f"      -> Pending #{o.ticket}: {o.symbol:<7} {t_name:<10} vol={o.volume_current} @ {o.price_open}")
                for p in mt5.positions_get() or []:
                    p_name = "BUY" if p.type == 0 else "SELL"
                    print(f"      -> Position #{p.ticket}: {p.symbol:<7} {p_name:<4} vol={p.volume} @ {p.price_open} | Profit: ${p.profit:+.2f}")
    mt5.shutdown()

print("=" * 90)