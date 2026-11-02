import json
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from app.core.config import settings


class ExecutionType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    HOLD = "NO_TRADE / WAIT"


class WebhookPayload(BaseModel):
    action: str = Field(description="BUY_LIMIT, SELL_LIMIT, BUY, SELL, or CLOSE")
    symbol: str
    volume_lots: float
    price: float
    sl: float
    tp1: float
    tp2: float
    comment: str


class QuantExecutionSignal(BaseModel):
    asset: str
    timeframe: str
    direction: str
    execution_type: ExecutionType
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pts: float
    reward_pts: float
    risk_reward_ratio: float
    expected_value: float
    recommended_lot_size: float
    quant_score: float = Field(ge=0.0, le=100.0)
    webhook_order: WebhookPayload
    telegram_formatted_report: str


NEXUS_SYSTEM_INSTRUCTION = """
You are NEXUS ELITE, Chief Quantitative Risk & Execution Officer.
Synthesize Oracle visual telemetry into an institutional algorithmic order specification.

EXECUTION & QUANT GOVERNANCE:
1. RISK PROFILE & BUFFER:
   - For Gold (XAUUSD), the Stop Loss MUST clear the structural pivot low or sweep high by at least 2.50 to 3.50 points.
2. POSITION SIZING ALGORITHM (Fractional Kelly / Fixed Fractional):
   - Baseline Account Size: $100,000 (standardized).
   - Maximum Risk Per Trade: 1.0% ($1,000 USD risk).
   - For XAUUSD: 1 Standard Lot = $100 per 1.00 pt price move ($10 per 0.10 pt).
   - Lot Formula: Lots = (Account_Risk_USD) / (Risk_Pts * 100).
   - Round to two decimal places (e.g. 1.07 lots).
3. WEBHOOK PAYLOAD CONSTRUCTION:
   - Generate a valid JSON payload for bridge execution (MetaTrader 5 / cTrader / Bybit).

TELEGRAM CARD SPECIFICATION:
⚡ *QUINT-NEXUS ELITE EXECUTION*
━━━━━━━━━━━━━━━━━━━━
🎯 *Asset:* {asset} | *TF:* {tf}
🔍 *Detection Engine:* {detection_mode}
📊 *Signal:* {direction} ({execution_type})
🏷️ *Live Tick:* {active_price} ({candle_timer} left)

📐 *ORDER MATRIX:*
• *Entry:* {entry_price}
• *Invalidation (SL):* {stop_loss} (Risk: -{risk_pts} pts)
• *Target 1 (TP1):* {tp1} (Reward: +{reward_pts} pts)
• *Target 2 (TP2):* {tp2}
• *RRR:* 1:{rrr:.2f} | *Expected Value:* +{ev:.2f}R
• *Quant Score:* {score}/100

💼 *POSITION SIZING (1.0% Risk / $100k Ref):*
• *Allocated Lots:* {lots} Lots
• *Max Exposure:* ${max_risk_usd:,.2f}

🔬 *MICRO-DRILLING CONFLUENCES:*
• *Tape/Delta:* {volume_readout}
• *Structure:* {structural_event}
• *Execution Thesis:* {thesis}
━━━━━━━━━━━━━━━━━━━━
"""


class NexusAgent:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-3.8-flash"

    def _validate_quant_boundaries(self, signal: QuantExecutionSignal) -> QuantExecutionSignal:
        """Enforces physical boundary invariants."""
        is_long = "LONG" in signal.direction.upper() or "BUY" in signal.direction.upper()
        is_short = "SHORT" in signal.direction.upper() or "SELL" in signal.direction.upper()

        if is_long and not (signal.stop_loss < signal.entry_price < signal.take_profit_1):
            signal.direction = "HOLD"
            signal.execution_type = ExecutionType.HOLD
            signal.telegram_formatted_report += "\n\n⚠️ *RISK GOVERNOR: Inverted Long Boundaries Rejected.*"
        elif is_short and not (signal.take_profit_1 < signal.entry_price < signal.stop_loss):
            signal.direction = "HOLD"
            signal.execution_type = ExecutionType.HOLD
            signal.telegram_formatted_report += "\n\n⚠️ *RISK GOVERNOR: Inverted Short Boundaries Rejected.*"
        return signal

    async def synthesize(
        self, 
        oracle_data: Any, 
        account_size_usd: float = 100000.0,
        risk_percentage: float = 1.0
    ) -> QuantExecutionSignal:
        oracle_str = oracle_data.model_dump_json() if hasattr(oracle_data, "model_dump_json") else json.dumps(oracle_data)

        user_prompt = f"""
        ORACLE EXTRACTED METRICS: {oracle_str}
        PORTFOLIO CONSTRAINTS:
        - Reference Account Capital: ${account_size_usd:,.2f}
        - Risk Allocation: {risk_percentage}%
        """

        config = types.GenerateContentConfig(
            system_instruction=NEXUS_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=QuantExecutionSignal,
            temperature=0.1,
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=config,
        )

        signal = QuantExecutionSignal.model_validate_json(response.text)
        return self._validate_quant_boundaries(signal)