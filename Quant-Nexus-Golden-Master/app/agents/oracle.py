import json
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from app.core.config import settings


class MarketBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class OrderBlock(BaseModel):
    timeframe: str
    price_high: float
    price_low: float
    ob_type: str = Field(description="Bullish or Bearish OB")
    is_mitigated: bool


class FairValueGap(BaseModel):
    timeframe: str
    top: float
    bottom: float
    mitigated: bool


class MicrostructureSchema(BaseModel):
    # Core Asset Identification
    asset: str = Field(description="Identified asset canonical symbol (e.g. XAUUSD, BTCUSDT, EURUSD, US500)")
    asset_identification_method: str = Field(
        description="Explicit Header OCR, Decimal/Tick Fingerprint, or Volatility Profile Match"
    )
    timeframe: str = Field(description="Timeframe (e.g., M1, M3, M5, M15, H1, H4, D1)")
    timeframe_derivation_logic: str = Field(
        description="Reasoning: Toolbar badge, countdown timer remaining ratio, or candle frequency"
    )

    # Micro-Price & Tape Coordinates
    active_price: float = Field(description="Exact live price coordinate on the right-hand vertical axis label")
    active_candle_timer: Optional[str] = Field(description="Remaining countdown time e.g., '00:33'")
    price_scale_step: float = Field(description="Visual distance between scale grid lines (e.g., 2.000 pts)")
    
    # Volume & Order-Flow Metrics
    volume_readout: str = Field(description="Bottom volume histogram numeric badge and delta color (e.g., '1.2 K Red Seller Delta')")
    volume_surge_ratio: float = Field(
        ge=0.0, 
        description="Estimated ratio of active bar volume compared to the visible rolling 20-bar average"
    )

    # SMC / ICT Advanced Microstructure
    market_bias: MarketBias
    structural_event: str = Field(description="BOS, CHoCH, Turtle Soup / Sweep, or Liquidity Raid")
    order_blocks: List[OrderBlock]
    fair_value_gaps: List[FairValueGap]
    sweep_invalidation_level: float = Field(description="Absolute lowest/highest structural wick level")
    confidence_score: float = Field(ge=0.0, le=1.0)


ORACLE_MICRO_DRILLING_PROMPT = """
You are ORACLE NEXT-GEN, an institutional visual quant engine executing micro-drilling financial chart deconstruction.
Even if headers, tickers, watermarks, or toolbars are cropped or hidden, identify the instrument and timeframe via statistical market mechanics.

======================================================================
1. DEEP MICRO-FINGERPRINTING (ASSET IDENTIFICATION WITHOUT HEADERS)
======================================================================
If the symbol header is obscured or missing, execute multi-factor price-scale fingerprinting:

A. DECIMAL PRECISION & PRICE BAND:
   - 4,000 - 4,500 band with 3 DECIMAL PLACES (e.g., 4,178.246, 4,175.740):
     * FINGERPRINT: XAUUSD (Gold Spot / USD).
     * Rule: Traditional equity indices (US500 / ES / SPX) do NOT trade with 3-decimal pricing; they quote in quarters (0.25, 0.50, 0.75, 0.00) or 2 decimals.
     * Scale Step: Gold increments often show intervals of 2.000 (4,180.000, 4,182.000, 4,184.000).
   - 80,000 - 150,000 band with 1 or 2 decimals: BTCUSDT.
   - 2,000 - 4,000 band with 2 decimals: ETHUSDT.
   - 1.0000 - 1.2500 band with 4 or 5 decimals (pipettes): EURUSD / GBPUSD.
   - 18,000 - 24,000 band: US100 / NAS100 / NQ.
   - 38,000 - 46,000 band: US30 / YM / Dow Jones.

B. VISUAL ICON CHECK:
   - Scan top-left for round tokens: Yellow/gold circle = XAUUSD; Orange B = BTC; Blue = Fiat/Index.

======================================================================
2. DYNAMIC TIMEFRAME (TF) RECONSTRUCTION
======================================================================
- Primary: Look for explicit badges: "1m", "3m", "5m", "15m", "1h", "4h".
- Micro-Timer Extraction:
  * Read the live countdown timer on the right axis beside the current price (e.g., "00:33", "01:55").
  * Deduce the interval:
    - If the timer displays minutes and seconds under 05:00 (e.g., "00:33" or "01:55") during active session movements, classify as Intraday Low Timeframe: M3 or M5.
    - If seconds count down from 60 seconds rapidly, classify as M1.
    - If timer indicates > 15:00, classify as H1.

======================================================================
3. MICRO-COORDINATE EXTRACTION
======================================================================
- ACTIVE TICK: Locate the filled color badge (red or green) anchored to the live price line on the right vertical scale. Read the exact number down to all visible decimal digits.
- VOLUME DELTA: Inspect the bottom-most sub-window:
  * Read the text label attached to the volume indicator (e.g., "1.2 K", "9.02 K", "14.5 M").
  * Determine bar color: Red = Net Seller Pressure, Green = Net Buyer Pressure.

======================================================================
4. INSTITUTIONAL SMC / ICT STRUCTURE EXTRACTION
======================================================================
- Differentiate between:
  * Continuation Break of Structure (BOS): Candle body closes beyond previous swing high/low.
  * Liquidity Sweep / Turtle Soup: Candle wick pierces swing high/low and immediately closes back inside the range with high opposite delta.
- Map exact high/low zones of unmitigated Order Blocks (OB) and Fair Value Gaps (FVG).
- Determine the true swing pivot invalidation level.

Output STRICT JSON conforming to MicrostructureSchema.
"""


class OracleAgent:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-3.8-flash"

    async def identify_and_analyze(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> MicrostructureSchema:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        config = types.GenerateContentConfig(
            system_instruction=ORACLE_MICRO_DRILLING_PROMPT,
            response_mime_type="application/json",
            response_schema=MicrostructureSchema,
            temperature=0.1,  # Low temperature for deterministic numerical parsing
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[image_part],
            config=config,
        )

        return MicrostructureSchema.model_validate_json(response.text)