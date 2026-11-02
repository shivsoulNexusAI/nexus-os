import MetaTrader5 as mt5
from engine_algorithmic import calculate_dynamic_kelly_risk

MAGIC_NUMBER = 999101

def inspect_kelly():
    if not mt5.initialize():
        print(f"❌ Failed to connect to MT5: {mt5.last_error()}")
        return

    dollar_risk, metrics = calculate_dynamic_kelly_risk(
        magic_number=MAGIC_NUMBER,
        lookback_days=30,
        default_risk_pct=0.01,
        base_kelly_fraction=0.35,
        min_risk_pct=0.005,
        max_risk_pct=0.025
    )

    print("\n" + "=" * 60)
    print("🛡️ QUANT NEXUS KELLY & DRAWDOWN TELEMETRY")
    print("=" * 60)
    print(f"• Current Equity:        ${metrics.get('equity', 0.0):,.2f}")
    print(f"• High-Water Mark (HWM): ${metrics.get('hwm', 0.0):,.2f}")
    print(f"• Peak Drawdown:         {metrics.get('drawdown_pct', 0.0)}%")
    print(f"• Throttle State:        {metrics.get('throttle_state', 'NORMAL')}")
    print(f"• Active Kelly Multiplier: {metrics.get('active_kelly_fraction', 0.35):.4f}")
    print(f"• Effective Risk Pct:    {metrics.get('risk_pct', 1.0)}%")
    print(f"• Allocated Dollar Risk: ${dollar_risk:,.2f}")
    print(f"• Trades in Sample:      {metrics.get('sample_size', 0)}")
    if metrics.get('sample_size', 0) >= 15:
        print(f"• Empirical Win Rate:    {metrics.get('win_rate', 0.0)}%")
        print(f"• Empirical Payoff (b):  {metrics.get('payoff_ratio', 0.0)}")
        print(f"• Full Kelly (f*):       {metrics.get('f_star', 0.0):.4f}")
    print("=" * 60 + "\n")

    mt5.shutdown()

if __name__ == "__main__":
    inspect_kelly()