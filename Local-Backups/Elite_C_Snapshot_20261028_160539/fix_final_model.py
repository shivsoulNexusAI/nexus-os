# Fix Oracle Agent to use the stable 'gemini-pro' model
oracle_code = """import google.generativeai as genai
from app.core.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

class OracleAgent:
    def __init__(self):
        # gemini-pro is the most stable, universally supported free vision model
        self.model = genai.GenerativeModel('gemini-pro')

    async def identify_and_analyze(self, image_bytes: bytes) -> str:
        prompt = "Analyze this trading chart. Identify asset, timeframe, SMC/ICT structure (OB, FVG, Liquidity). Output strict JSON."
        response = self.model.generate_content([prompt, {"mime_type": "image/jpeg", "data": image_bytes}])
        return response.text
"""
with open("app/agents/oracle.py", "w", encoding="utf-8") as f:
    f.write(oracle_code)

# Fix Nexus Agent to use the stable 'gemini-pro' model
nexus_code = """import google.generativeai as genai
from app.core.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

class NexusAgent:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-pro')

    async def synthesize(self, oracle_data: str, quant_data: dict, mcp_data: str, user_tier: str) -> str:
        prompt = f"Combine into Telegram report. ORACLE: {oracle_data}, QUANT: {quant_data}, MACRO: {mcp_data}. Format: Asset, TF, Bias, SMC, Volume, Direction, Score, Entry, SL, TP."
        response = self.model.generate_content(prompt)
        return response.text
"""
with open("app/agents/nexus.py", "w", encoding="utf-8") as f:
    f.write(nexus_code)

print("SUCCESS: Model names updated to stable 'gemini-pro'")
