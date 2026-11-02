import datetime

def check_ecosystem_status(user_id: int) -> dict:
    return {"user_id": user_id, "status": "Active"}

def fetch_macro_news(asset: str) -> dict:
    return {"asset": asset, "news": "No high impact news."}

MCP_TOOLS_REGISTRY = {
    "check_ecosystem_status": check_ecosystem_status,
    "fetch_macro_news": fetch_macro_news
}
