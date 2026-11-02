import os
import sqlite3
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "quant_nexus_super_secret_jwt_key_2026")
JWT_ALGORITHM = "HS256"
DB_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot\quant_metrics.db"

# Bearer token extractor from Authorization header
security_scheme = HTTPBearer()

# Tier rank weights for strict hierarchical inheritance
TIER_HIERARCHY = {
    "FREE": 1,
    "PRO": 2,
    "ELITE": 3
}

class AuthenticatedUser(BaseModel):
    telegram_id: int
    username: Optional[str] = ""
    tier: str
    reputation_score: float = 1.0

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> AuthenticatedUser:
    """
    Decodes the Bearer JWT token, validates signature/expiration,
    and queries the database for the user's latest tier and reputation.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        telegram_id_str = payload.get("sub")
        if telegram_id_str is None:
            raise credentials_exception
        telegram_id = int(telegram_id_str)
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    # Query latest state from database (in case of tier upgrade/demotion mid-session)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, tier, reputation_score FROM community_users WHERE telegram_id = ?",
        (telegram_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authenticated user record not found in database."
        )

    return AuthenticatedUser(
        telegram_id=telegram_id,
        username=row[0] or "",
        tier=row[1] or "FREE",
        reputation_score=float(row[2] or 1.0)
    )

def require_tier(minimum_tier: str):
    """
    Factory dependency enforcing hierarchical tier access:
    - 'FREE' allows FREE, PRO, ELITE
    - 'PRO' allows PRO, ELITE
    - 'ELITE' allows ELITE only
    """
    required_rank = TIER_HIERARCHY.get(minimum_tier.upper(), 1)

    def tier_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        user_rank = TIER_HIERARCHY.get(current_user.tier.upper(), 1)
        if user_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted. Requires '{minimum_tier}' tier or higher (Current: '{current_user.tier}')."
            )
        return current_user

    return tier_checker