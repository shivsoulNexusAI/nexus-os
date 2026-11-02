from app.api.mcp_tools import MCP_TOOLS_REGISTRY
import json

class MCPRouter:
    """
    The MCP Router acts as the bridge between the AI (Nexus Agent) 
    and the external world (Tools).
    """
    
    @staticmethod
    def get_tool_definitions():
        """Returns the tool schemas so the AI knows what it can call."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "fetch_macro_news",
                    "description": "Fetches high-impact economic news for a specific asset",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "asset": {"type": "string", "description": "The asset symbol, e.g., XAUUSD"}
                        },
                        "required": ["asset"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_ecosystem_status",
                    "description": "Checks user status in the Shivsoul Ecosystem",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "integer", "description": "Telegram user ID"}
                        },
                        "required": ["user_id"]
                    }
                }
            }
        ]

    @staticmethod
    def execute_tool(tool_name: str, arguments: dict):
        """Executes the requested tool and returns the result to the AI."""
        if tool_name in MCP_TOOLS_REGISTRY:
            try:
                # Execute the function with the arguments provided by the AI
                result = MCP_TOOLS_REGISTRY[tool_name](**arguments)
                return json.dumps(result)
            except Exception as e:
                return json.dumps({"error": str(e)})
        return json.dumps({"error": "Tool not found"})
