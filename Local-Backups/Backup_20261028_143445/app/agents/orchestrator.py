import asyncio
import json
from app.agents.oracle import OracleAgent
from app.agents.quant import QuantAgent
from app.agents.nexus import NexusAgent
from app.api.mcp_router import MCPRouter

class QuantumOrchestrator:
    def __init__(self):
        self.oracle = OracleAgent()
        self.quant = QuantAgent()
        self.nexus = NexusAgent()
        self.mcp = MCPRouter()

    async def process_upload(self, image_bytes: bytes, user_tier: str = "Free") -> str:
        """Main pipeline: Blind Vision -> Parallel Data Fetch -> MCP Enrichment -> Synthesis"""
        
        # Phase 1: Blind Vision (Identify Asset & Visual Structure)
        oracle_data = await self.oracle.identify_and_analyze(image_bytes)
        
        # Extract asset name from oracle data (simplified parsing for now)
        # In production, we'd parse the JSON strictly. Here we assume it returns a dict or string we can search.
        asset_symbol = "XAUUSD" # Fallback default
        
        # Phase 2: Parallel Data Fetch (The Speed Layer)
        quant_task = self.quant.fetch_order_flow(asset_symbol, "M15")
        
        # Phase 3: MCP Enrichment (Fetch Macro News for context)
        mcp_task = asyncio.to_thread(self.mcp.execute_tool, "fetch_macro_news", {"asset": asset_symbol})
        
        # Run Quant and MCP simultaneously
        quant_data, mcp_data = await asyncio.gather(quant_task, mcp_task)
        
        # Phase 4: Synthesis (The Intelligence Layer)
        final_report = await self.nexus.synthesize(oracle_data, quant_data, mcp_data, user_tier)
        
        return final_report

# Global instance for the bot to use
quantum_engine = QuantumOrchestrator()
