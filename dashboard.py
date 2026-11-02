# -*- coding: utf-8 -*-
"""
SHIVSOUL QUANTITATIVE MISSION CONTROL - DESK DASHBOARD
Real-Time Multi-Asset Telemetry, ML Regime Oversight & Shadow vs. Live Comparison
"""

import os
import json
import time
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import streamlit as st
import MetaTrader5 as mt5

st.set_page_config(
    page_title="Nexus Institutional Desk | Mission Control",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- DATA LOADERS -----------------
SHADOW_PORTFOLIO_FILE = "shadow_portfolio.json"
SHADOW_JOURNAL_FILE = "shadow_journal.csv"
CONFIG_FILE = "threshold_config.json"
ACCOUNTS_FILE = "accounts.json"

def get_mt5_account_data():
    if not mt5.initialize():
        return None, None
    acc = mt5.account_info()
    positions = mt5.positions_get()
    return acc, positions

def get_shadow_data():
    portfolio = {"balance": 10000.0, "equity": 10000.0, "positions": {}}
    if os.path.exists(SHADOW_PORTFOLIO_FILE):
        try:
            with open(SHADOW_PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                portfolio = json.load(f)
        except Exception:
            pass

    journal_df = pd.DataFrame()
    if os.path.exists(SHADOW_JOURNAL_FILE):
        try:
            journal_df = pd.read_csv(SHADOW_JOURNAL_FILE)
            if not journal_df.empty and "exit_time" in journal_df.columns:
                journal_df["exit_time"] = pd.to_datetime(journal_df["exit_time"])
        except Exception:
            pass
            
    return portfolio, journal_df

def get_live_history_df():
    # Pull recent closed deals from MT5 for live equity comparison
    if not mt5.initialize():
        return pd.DataFrame()
    utc_from = datetime.now(timezone.utc) - pd.Timedelta(days=30)
    deals = mt5.history_deals_get(utc_from, datetime.now(timezone.utc))
    if deals is None or len(deals) == 0:
        return pd.DataFrame()
    
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df = df[df["entry"] == 1]  # Out trades only
    if df.empty:
        return pd.DataFrame()
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["dollar_pnl"] = df["profit"] + df["swap"] + df["fee"]
    return df

# ----------------- UI HEADER -----------------
st.title("⚡ SHIVSOUL MISSION CONTROL")
st.caption("Institutional Quantitative Desk • Multi-Asset Sovereign Execution • Machine Learning Governance")

# Polling loop / auto-refresh selector in sidebar
with st.sidebar:
    st.header("Desk Controls")
    auto_refresh = st.checkbox("Live Polling (3s)", value=True)
    if st.button("Manual Force Sync"):
        st.rerun()
    st.divider()
    
    # Active Account Info
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                acc_cfg = json.load(f)
                st.markdown(f"**Active Account Alias:** `{acc_cfg.get('active_alias', 'main').upper()}`")
        except Exception:
            pass

acc, open_positions = get_mt5_account_data()
shadow_portfolio, shadow_journal = get_shadow_data()

# ----------------- TOP METRICS: LIVE VS SHADOW -----------------
m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)

live_balance = acc.balance if acc else 0.0
live_equity = acc.equity if acc else 0.0
live_open_count = len(open_positions) if open_positions else 0

shadow_balance = shadow_portfolio.get("balance", 10000.0)
shadow_positions = shadow_portfolio.get("positions", {})
shadow_open_count = len(shadow_positions)

# Estimate unrealized shadow equity
shadow_unrealized = 0.0
if mt5.initialize():
    for pos in shadow_positions.values():
        tick = mt5.symbol_info_tick(pos["symbol"])
        if tick:
            cur_price = tick.bid if pos["direction"] == "BUY" else tick.ask
            r_gain = (cur_price - pos["entry_price"]) / pos["sl_dist"] if pos["direction"] == "BUY" else (pos["entry_price"] - cur_price) / pos["sl_dist"]
            shadow_unrealized += r_gain * pos.get("dollar_risk", 0.0)

shadow_equity = shadow_balance + shadow_unrealized

with m_col1:
    st.metric("Live Equity", f"${live_equity:,.2f}", delta=f"{((live_equity-live_balance)/live_balance*100):+.2f}%" if live_balance else "0%")
with m_col2:
    st.metric("Live Tickets", f"{live_open_count} Open", delta="Market Active" if live_open_count > 0 else "Flat")
with m_col3:
    st.metric("Shadow Equity", f"${shadow_equity:,.2f}", delta=f"{shadow_unrealized:+.2f} USD")
with m_col4:
    st.metric("Shadow Tickets", f"{shadow_open_count} Virtual", delta="Paper Lab Active" if shadow_open_count > 0 else "Flat")
with m_col5:
    # Alpha Attribution (Vetoes Blocked)
    veto_count = len(shadow_journal[shadow_journal["outcome"] == "ML_VETO_BLOCKED"]) if not shadow_journal.empty and "outcome" in shadow_journal.columns else 0
    st.metric("ML Veto Shield", f"{veto_count} Suppressed", delta="Capital Saved", delta_color="normal")

st.divider()

# ----------------- TABS INTERFACE -----------------
tab_perf, tab_shadow, tab_live, tab_governance = st.tabs([
    "📈 Comparative Performance (Shadow vs Live)",
    "🧪 Shadow Forward Lab",
    "💼 Live Production Desk",
    "🛡️ ML Regime Governor"
])

# ----- TAB 1: SHADOW VS LIVE EQUITY CURVES -----
with tab_perf:
    st.subheader("Normalized Capital Trajectory: Forward Shadow vs. Production Live")
    
    # Build Time-Series Comparison
    live_df = get_live_history_df()
    
    chart_data = pd.DataFrame()
    
    # Process Shadow Equity Progression
    if not shadow_journal.empty and "final_balance" in shadow_journal.columns:
        valid_shadow = shadow_journal[shadow_journal["outcome"] != "ML_VETO_BLOCKED"].copy()
        if not valid_shadow.empty:
            valid_shadow = valid_shadow.sort_values("exit_time")
            valid_shadow["Shadow Balance"] = valid_shadow["final_balance"]
            shadow_series = valid_shadow.set_index("exit_time")["Shadow Balance"]
            chart_data = pd.concat([chart_data, shadow_series], axis=1)

    # Process Live Realized PnL Progression
    if not live_df.empty:
        live_df = live_df.sort_values("time")
        live_df["Live Balance"] = live_balance - live_df["dollar_pnl"].iloc[::-1].cumsum().iloc[::-1] + live_df["dollar_pnl"]
        live_series = live_df.set_index("time")["Live Balance"]
        chart_data = pd.concat([chart_data, live_series], axis=1)

    if not chart_data.empty:
        chart_data = chart_data.ffill().bfill()
        st.line_chart(chart_data)
    else:
        st.info("Insufficient multi-trade closed history to project comparative line chart. Run the Shadow Tracker or close trades to populate.")

    # Performance Audit Table
    st.markdown("### Institutional Metric Breakdown")
    p_col1, p_col2 = st.columns(2)
    
    with p_col1:
        st.markdown("**Live Account Statistics**")
        if not live_df.empty:
            wins = live_df[live_df["dollar_pnl"] > 0]
            losses = live_df[live_df["dollar_pnl"] < 0]
            pf = round(wins["dollar_pnl"].sum() / (abs(losses["dollar_pnl"].sum()) + 1e-9), 2)
            wr = round(len(wins) / len(live_df) * 100, 1)
            st.write(f"- **Total Closed:** {len(live_df)}")
            st.write(f"- **Win Rate:** {wr}%")
            st.write(f"- **Profit Factor:** {pf}")
            st.write(f"- **Net Profit:** ${live_df['dollar_pnl'].sum():+,.2f}")
        else:
            st.write("No closed live trades found in 30-day window.")

    with p_col2:
        st.markdown("**Shadow Engine Statistics (Forward Paper)**")
        if not shadow_journal.empty and "outcome" in shadow_journal.columns:
            completed_shadow = shadow_journal[shadow_journal["outcome"].isin(["WIN", "LOSS", "BREAKEVEN"])]
            s_wins = completed_shadow[completed_shadow["outcome"] == "WIN"]
            s_losses = completed_shadow[completed_shadow["outcome"] == "LOSS"]
            s_bes = completed_shadow[completed_shadow["outcome"] == "BREAKEVEN"]
            
            s_pf = round(s_wins["dollar_pnl"].sum() / (abs(s_losses["dollar_pnl"].sum()) + 1e-9), 2) if not s_losses.empty else 0.0
            s_wr = round(len(s_wins) / (len(completed_shadow) + 1e-9) * 100, 1)
            
            st.write(f"- **Total Paper Setups:** {len(completed_shadow)}")
            st.write(f"- **Win Rate:** {s_wr}% (BEs: {len(s_bes)})")
            st.write(f"- **Paper Profit Factor:** {s_pf}")
            st.write(f"- **Paper Return:** ${(shadow_balance - 10000.0):+,.2f}")
        else:
            st.write("No completed shadow trades in journal.")

# ----- TAB 2: SHADOW FORWARD LAB DETAIL -----
with tab_shadow:
    st.subheader("Active Virtual Orders in Memory")
    if shadow_positions:
        s_rows = []
        for tid, p in shadow_positions.items():
            s_rows.append({
                "Ticket": tid[:12],
                "Symbol": p["symbol"],
                "Direction": p["direction"],
                "Edge Score": f"{p['edge']}%",
                "ML Regime": p.get("ml_regime", "UNKNOWN"),
                "Entry Price": f"{p['entry_price']:.5f}",
                "SL": f"{p['sl']:.5f}",
                "TP": f"{p['tp']:.5f}",
                "Breakeven Shift": "ACTIVE" if p.get("be_active") else "Pending (+1.0R)",
                "Allocated Risk": f"${p['dollar_risk']:.2f}"
            })
        st.dataframe(pd.DataFrame(s_rows), width="stretch")
    else:
        st.info("No active virtual shadow orders currently open.")

    st.subheader("Shadow Journal History (Latest 15 Events)")
    if not shadow_journal.empty:
        st.dataframe(shadow_journal.tail(15).iloc[::-1], width="stretch")
    else:
        st.caption("Journal empty.")

# ----- TAB 3: LIVE PRODUCTION DESK -----
with tab_live:
    st.subheader("🏛️ Nexus Omega: Institutional Live Production Desk")

    # 1. PILLAR 2: HARD CIRCUIT BREAKER & ROLLOVER STATUS
    c_b1, c_b2, c_b3 = st.columns(3)
    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals_today = mt5.history_deals_get(today_utc, datetime.now(timezone.utc)) if mt5.initialize() else []
    closed_deals = [d for d in (deals_today or []) if d.entry == 1 and (d.magic == 888999 or abs(d.profit) > 0.0001)]
    realized_today = sum(d.profit for d in closed_deals)
    is_tripped = realized_today <= -300.0

    with c_b1:
        if is_tripped:
            st.error("🚨 Daily Circuit Breaker: TRIPPED (LOCKED)")
        else:
            st.success("🛡️ Daily Circuit Breaker: ARMED (NORMAL)")
        st.caption("Hard-gated at -.00 Max Daily Loss")

    with c_b2:
        st.metric("Today Realized PnL", f"", delta=f"{len(closed_deals)} Closed Deals")
        st.caption("Auto-resets daily at 00:00 UTC")

    with c_b3:
        if acc:
            st.metric("Live Margin Level", f"{(acc.margin_level):,.1f}%", delta=f"\ Equity")
            st.caption(f"Balance: \ | Free Margin: ")

    st.markdown("---")

    # 2. PILLAR 1: ASYMMETRIC STACKING RADAR (+1.50R TARGETS)
    st.subheader("🎯 Pillar 1: Asymmetric Invalidation Stacking Radar")
    if open_positions:
        stacking_cards = st.columns(len(open_positions))
        for idx, pos in enumerate(open_positions):
            sym = pos.symbol
            risk_dist = 0.0020
            if "JPY" in sym: risk_dist = 0.200
            elif "XAU" in sym: risk_dist = 5.00
            elif "BTC" in sym: risk_dist = 150.0

            p_type = "BUY" if pos.type == 0 else "SELL"
            cur_dist = (pos.price_current - pos.price_open) if pos.type == 0 else (pos.price_open - pos.price_current)
            cur_r = cur_dist / risk_dist
            dist_to_harvest = 1.5 - cur_r

            # Check Breakeven status
            is_be = abs(pos.sl - pos.price_open) <= (risk_dist * 0.1) if pos.sl > 0 else False

            with stacking_cards[idx]:
                st.markdown(f"**Ticket #{pos.ticket} ({sym} {p_type})**")
                st.metric("Current R-Multiple", f"{cur_r:+.2f}R", delta=f"")
                if is_be:
                    st.success("🛡️ BREAKEVEN LOCKED (Risk-Free)")
                else:
                    st.info(f"Open SL: {pos.sl:.5f}")

                if dist_to_harvest <= 0:
                    st.success("🚀 READY FOR 50% HARVEST + 0.5x STACK")
                else:
                    st.caption(f"Distance to +1.50R Harvest: **{dist_to_harvest:+.2f}R**")
    else:
        st.info("No open positions awaiting stacking evaluation.")

    st.markdown("---")

    # 3. LIVE MT5 EXECUTION BOOK
    st.subheader("📋 Active Monitored Live Tickets")
    if open_positions:
        live_rows = []
        for pos in open_positions:
            sym = pos.symbol
            risk_dist = 0.200 if "JPY" in sym else (5.00 if "XAU" in sym else (150.0 if "BTC" in sym else 0.0020))
            cur_dist = (pos.price_current - pos.price_open) if pos.type == 0 else (pos.price_open - pos.price_current)
            cur_r = cur_dist / risk_dist

            live_rows.append({
                "Ticket": pos.ticket,
                "Symbol": pos.symbol,
                "Type": "BUY" if pos.type == 0 else "SELL",
                "Volume": pos.volume,
                "Open Price": pos.price_open,
                "Current Price": pos.price_current,
                "Current R": f"{cur_r:+.2f}R",
                "SL": pos.sl,
                "TP": pos.tp,
                "Floating Profit": f""
            })
        st.dataframe(pd.DataFrame(live_rows), width="stretch")
    else:
        st.info("No live open tickets in MT5.")

# ----- TAB 4: ML REGIME GOVERNOR -----
with tab_governance:
    st.subheader("Gaussian Mixture Model Regime Matrix")
    
    symbols_to_check = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
    g_rows = []
    
    try:
        from regime_governor import RegimeGovernor
        gov = RegimeGovernor()
        for s in symbols_to_check:
            res = gov.evaluate(s)
            g_rows.append({
                "Symbol": s,
                "Regime": res["regime"],
                "Verdict": res["verdict"],
                "Confidence": f"{res['confidence']*100:.1f}%",
                "Risk Multiplier": f"{res.get('risk_multiplier', 1.0)}x",
                "Efficiency Ratio": res.get("efficiency", 0.0),
                "ATR Ratio": res.get("atr_ratio", 1.0)
            })
        st.dataframe(pd.DataFrame(g_rows), width="stretch")
    except Exception as e:
        st.error(f"Regime Governor offline: {e}")

# Continuous background update
if auto_refresh:
    time.sleep(3)
    st.rerun()