# Mock User Model (SQLAlchemy temporarily disabled to bypass Windows DLL block)
from app.core.config import settings

async def get_user_tier(telegram_id: int) -> str:
    if telegram_id == settings.ADMIN_TELEGRAM_ID:
        return "Quantum_Elite"
    return "Free"
