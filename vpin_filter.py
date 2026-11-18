import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime, timezone


class VPINToxicityFilter:
    def __init__(self, bucket_volume: float = 50.0, window_size: int = 40, adverse_threshold: float = 0.65):
        self.bucket_volume = bucket_volume
        self.window_size = window_size
        self.adverse_threshold = adverse_threshold

    def compute_directional_vpin(self, symbol: str, direction: str, num_recent_ticks: int = 10000) -> dict:
        if not mt5.terminal_info():
            return {"error": "MT5 not initialized", "vpin": 0.0, "signed_vpin": 0.0, "adverse_toxic": False}

        now = datetime.now(timezone.utc)
        ticks = mt5.copy_ticks_from(symbol, now, num_recent_ticks, mt5.COPY_TICKS_ALL)

        df = pd.DataFrame()
        if ticks is not None and len(ticks) > 0:
            df_raw = pd.DataFrame(ticks)
            price_col = "last" if ("last" in df_raw.columns and df_raw["last"].sum() > 0) else ("bid" if "bid" in df_raw.columns else None)
            vol_col = "volume" if "volume" in df_raw.columns else None
            if price_col and vol_col:
                df = pd.DataFrame({
                    "price": df_raw[price_col].astype(float),
                    "volume": df_raw[vol_col].astype(float),
                })
                df = df[df["volume"] > 0.0]

        if df.empty:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 120)
            if rates is not None and len(rates) > 0:
                df_rates = pd.DataFrame(rates)
                vols = df_rates["tick_volume"].astype(float)
                if vols.sum() <= 0:
                    vols = pd.Series([1.0] * len(df_rates))
                df = pd.DataFrame({"price": df_rates["close"].astype(float), "volume": vols})

        if df.empty:
            return {"symbol": symbol, "vpin": 0.0, "signed_vpin": 0.0, "adverse_toxic": False}

        df["price_diff"] = df["price"].diff()
        df["sign"] = np.sign(df["price_diff"]).replace(0, np.nan).ffill().fillna(1.0)
        df["buy_vol"] = np.where(df["sign"] > 0, df["volume"], 0.0)
        df["sell_vol"] = np.where(df["sign"] < 0, df["volume"], 0.0)

        # Adaptive bucket size = 1/50th of recent total volume so FX, Gold, and BTC scale naturally
        total_vol = float(df["volume"].sum())
        adaptive_bucket = max(1.0, total_vol / 50.0)

        buckets = []
        cur_buy = cur_sell = cur_vol = 0.0
        for b_v, s_v, t_v in zip(df["buy_vol"].to_numpy(), df["sell_vol"].to_numpy(), df["volume"].to_numpy()):
            while cur_vol + t_v >= adaptive_bucket:
                frac = (adaptive_bucket - cur_vol) / max(t_v, 1e-9)
                cur_buy += b_v * frac
                cur_sell += s_v * frac
                buckets.append((cur_buy, cur_sell, abs(cur_buy - cur_sell), cur_buy - cur_sell))
                t_v -= (adaptive_bucket - cur_vol)
                b_v *= (1.0 - frac)
                s_v *= (1.0 - frac)
                cur_buy = cur_sell = cur_vol = 0.0
            cur_buy += b_v
            cur_sell += s_v
            cur_vol += t_v

        if not buckets:
            return {"symbol": symbol, "vpin": 0.0, "signed_vpin": 0.0, "adverse_toxic": False}

        win = buckets[-self.window_size:]
        denom = len(win) * adaptive_bucket
        unsigned_vpin = sum(x[2] for x in win) / denom
        signed_vpin = sum(x[3] for x in win) / denom  # +1 = pure buy pressure, -1 = pure sell pressure

        dir_sign = 1.0 if direction == "BUY" else (-1.0 if direction == "SELL" else 0.0)
        aligned_flow = signed_vpin * dir_sign
        # Toxic ONLY when strong flow is actively opposing our intended direction
        adverse_toxic = (dir_sign != 0.0) and (aligned_flow <= -self.adverse_threshold)

        return {
            "symbol": symbol,
            "vpin": round(float(unsigned_vpin), 4),
            "signed_vpin": round(float(signed_vpin), 4),
            "aligned_flow": round(float(aligned_flow), 4),
            "adverse_toxic": bool(adverse_toxic),
            "threshold": self.adverse_threshold,
        }
