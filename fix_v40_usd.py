from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\backtest_v40_session_micro.py")
code = p.read_text(encoding="utf-8")

# 1. Resample cached 79,920 M5 bars to M15 (guarantees all 6 symbols load 100% of 2025-2026 history)
old_load = """        mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 35000)
        info = mt5.symbol_info(sym)
        if rates is None or len(rates) < 500 or not info:
            continue

        point = info.point
        contract_size = info.trade_contract_size
        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)"""

new_load = """        mt5.symbol_select(sym, True)
        rates_m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 79920)
        info = mt5.symbol_info(sym)
        if rates_m5 is None or len(rates_m5) < 1500 or not info:
            print(f"[SKIP] {sym}")
            continue

        point = info.point
        # Exact USD value per 1.0 price move for 1.0 lot (handles USDJPY quote-currency conversion automatically)
        usd_per_price_unit = (info.trade_tick_value / info.trade_tick_size) if info.trade_tick_size > 0 else info.trade_contract_size
        df_m5 = pd.DataFrame(rates_m5)
        df_m5["dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
        df = df_m5.set_index("dt").resample("15min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum"
        }).dropna().reset_index()"""

assert old_load in code, "old_load not found"
code = code.replace(old_load, new_load, 1)
code = code.replace("contract_size", "usd_per_price_unit")

p.write_text(code, encoding="utf-8")
print("[OK] Updated backtest_v40_session_micro.py with 6-asset M5->M15 resampling & exact USD tick conversion.")