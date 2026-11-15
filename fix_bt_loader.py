from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\backtest_v31_2025_2026.py")
code = p.read_text(encoding="utf-8")

old_fetch = """def prepare_symbol_df(symbol: str, bundle) -> pd.DataFrame | None:
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, START_DT, END_DT)
    if rates is None or len(rates) < 500:
        print(f"[SKIP] {symbol}: insufficient M5 history ({0 if rates is None else len(rates)} bars).")
        return None"""

new_fetch = """def prepare_symbol_df(symbol: str, bundle) -> pd.DataFrame | None:
    mt5.symbol_select(symbol, True)
    rates = None
    for bar_count in (200000, 120000, 80000, 50000, 25000, 10000):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bar_count)
        if rates is not None and len(rates) >= 500:
            break
    if rates is None or len(rates) < 500:
        print(f"[SKIP] {symbol}: insufficient M5 history ({0 if rates is None else len(rates)} bars, err={mt5.last_error()}).")
        return None"""

assert old_fetch in code, "old_fetch not found"
code = code.replace(old_fetch, new_fetch, 1)

old_print = """    for r in (res_base, res_v31):
        print("\\n" + "-" * 92)
        print(f"MODEL: {r['label']}")
        print(f"Trades: {r['trades']} | Win Rate: {r.get('win_rate_pct')}% | Net PnL: ${r.get('net_pnl'):+,.2f} | "
              f"Profit Factor: {r.get('profit_factor')} | Max DD: ${r.get('max_dd_usd'):,.2f}")"""

new_print = """    for r in (res_base, res_v31):
        print("\\n" + "-" * 92)
        print(f"MODEL: {r['label']}")
        if r.get("trades", 0) == 0:
            print("Trades: 0 (No data loaded)")
            continue
        print(f"Trades: {r['trades']} | Win Rate: {r.get('win_rate_pct', 0.0)}% | Net PnL: ${r.get('net_pnl', 0.0):+,.2f} | "
              f"Profit Factor: {r.get('profit_factor', 0.0)} | Max DD: ${r.get('max_dd_usd', 0.0):,.2f}")"""

assert old_print in code, "old_print not found"
code = code.replace(old_print, new_print, 1)

p.write_text(code, encoding="utf-8")
print("[OK] Patched backtest_v31_2025_2026.py to use copy_rates_from_pos.")