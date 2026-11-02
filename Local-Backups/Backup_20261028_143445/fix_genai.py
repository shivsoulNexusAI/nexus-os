# 1. Fix Oracle Agent with NEW google-genai SDK
oracle_code = """from google import genai
from google.genai import types
from app.core.config import settings

class OracleAgent:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def identify_and_analyze(self, image_bytes: bytes) -> str:
        prompt = "Analyze this trading chart. Identify asset, timeframe, SMC/ICT structure (OB, FVG, Liquidity). Output strict JSON."
        response = self.client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')]
        )
        return response.text
"""
with open("app/agents/oracle.py", "w", encoding="utf-8") as f:
    f.write(oracle_code)

# 2. Fix Nexus Agent with NEW google-genai SDK
nexus_code = """from google import genai
from app.core.config import settings

class NexusAgent:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def synthesize(self, oracle_data: str, quant_data: dict, mcp_data: str, user_tier: str) -> str:
        prompt = f"Combine into Telegram report. ORACLE: {oracle_data}, QUANT: {quant_data}, MACRO: {mcp_data}. Format: Asset, TF, Bias, SMC, Volume, Direction, Score, Entry, SL, TP."
        response = self.client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[prompt]
        )
        return response.text
"""
with open("app/agents/nexus.py", "w", encoding="utf-8") as f:
    f.write(nexus_code)

print("SUCCESS: Switched to new google-genai SDK and gemini-3.8-flash model!")
