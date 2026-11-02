import os
import time
import hmac
import hashlib
import sqlite3
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
from dotenv import load_dotenv

load_dotenv(override=True)

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "quant_nexus_super_secret_jwt_key_2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7-day session token
DB_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot\quant_metrics.db"

app = FastAPI(title="Quant Nexus Auth & Telegram SSO Service", version="1.0.0")

# Enable CORS for the future dashboard frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------
class TelegramLoginPayload(BaseModel):
    id: int
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    username: Optional[str] = ""
    photo_url: Optional[str] = ""
    auth_date: int
    hash: str

class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str
    telegram_id: int
    tier: str

# ------------------------------------------------------------------------------
# Cryptographic Validation Core
# ------------------------------------------------------------------------------
def verify_telegram_signature(data: dict, bot_token: str) -> bool:
    """
    Verifies data received via the Telegram Login Widget according to official spec:
    1. Sort keys alphabetically (excluding 'hash').
    2. Format as 'key=value\n'.
    3. Generate secret_key = SHA256(bot_token).
    4. Compute HMAC_SHA256(secret_key, data_check_string).
    """
    received_hash = data.get("hash")
    if not received_hash or not bot_token:
        return False

    # Prevent replay attacks: ensure request is not older than 24 hours
    current_time = int(time.time())
    auth_date = int(data.get("auth_date", 0))
    if current_time - auth_date > 86400:
        return False

    # Build data-check string
    items = []
    for k, v in sorted(data.items()):
        if k != "hash" and v is not None and v != "":
            items.append(f"{k}={v}")
    data_check_string = "\n".join(items)

    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_hash, received_hash)

# ------------------------------------------------------------------------------
# Database User Resolution
# ------------------------------------------------------------------------------
def upsert_user(telegram_id: int, username: str, first_name: str) -> str:
    """
    Persists user to SQLite and returns their current tier (FREE, PRO, or ELITE).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            tier TEXT DEFAULT 'FREE' CHECK(tier IN ('FREE', 'PRO', 'ELITE')),
            reputation_score REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Upsert user without overwriting tier or reputation
    cursor.execute("""
        INSERT INTO community_users (telegram_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (telegram_id, username, first_name))
    conn.commit()

    cursor.execute("SELECT tier FROM community_users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()

    return row[0] if row else "FREE"

# ------------------------------------------------------------------------------
# JWT Generation
# ------------------------------------------------------------------------------
def issue_jwt_session(telegram_id: int, username: str, tier: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(telegram_id),
        "username": username,
        "tier": tier,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# ------------------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------------------
@app.post("/api/v1/auth/telegram", response_model=AuthTokenResponse)
def telegram_login_callback(payload: TelegramLoginPayload):
    """
    Endpoint receiving data from the Telegram Login Widget callback.
    Validates HMAC signature, records user, and issues a JWT token.
    """
    payload_dict = payload.model_dump()

    # 1. Cryptographic Verification
    is_valid = verify_telegram_signature(payload_dict, BOT_TOKEN)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cryptographic verification failed: invalid hash or expired auth payload."
        )

    # 2. Upsert User in SQLite
    user_tier = upsert_user(
        telegram_id=payload.id,
        username=payload.username or "",
        first_name=payload.first_name or ""
    )

    # 3. Mint JWT Token
    token = issue_jwt_session(
        telegram_id=payload.id,
        username=payload.username or "",
        tier=user_tier
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "telegram_id": payload.id,
        "tier": user_tier
    }

@app.get("/health")
def health_check():
    return {"status": "ONLINE", "service": "Quant Nexus SSO Gateway"}

from security import get_current_user, require_tier, AuthenticatedUser

# ------------------------------------------------------------------------------
# Tier-Protected Analytical Endpoints (Shivsoul Moat)
# ------------------------------------------------------------------------------

@app.get("/api/v1/feed/free")
def get_free_feed(user: AuthenticatedUser = Depends(require_tier("FREE"))):
    """
    Free Tier: Market bias and delayed structural summary.
    """
    return {
        "user_tier": user.tier,
        "access": "GRANTED_FREE",
        "market_bias": "BULLISH_BIAS",
        "session": "LONDON_OPEN",
        "summary": "15-minute delayed structure showing higher lows on Gold."
    }

@app.get("/api/v1/feed/pro")
def get_pro_feed(user: AuthenticatedUser = Depends(require_tier("PRO"))):
    """
    Pro Tier: Full execution zones (Entry, SL, TP) + Volume Profile (POC/VAH/VAL).
    """
    return {
        "user_tier": user.tier,
        "access": "GRANTED_PRO",
        "asset": "XAUUSD",
        "execution": {
            "entry": 2684.50,
            "stop_loss": 2675.00,
            "take_profit_1": 2695.00,
            "take_profit_2": 2705.00
        },
        "volume_profile": {
            "poc": 2681.20,
            "vah": 2692.00,
            "val": 2673.50
        }
    }

@app.get("/api/v1/feed/elite")
def get_elite_feed(user: AuthenticatedUser = Depends(require_tier("ELITE"))):
    """
    Elite Tier: Live Order Flow (CVD), Liquidation Clusters, and Raw Quantum Score.
    """
    return {
        "user_tier": user.tier,
        "access": "GRANTED_ELITE",
        "asset": "XAUUSD",
        "quantum_score": 94.2,
        "order_flow": {
            "cvd_divergence": "BULLISH_ABSORPTION",
            "delta_imbalance": "+3,420 contracts"
        },
        "liquidation_heatmap": {
            "overhead_liquidity_pool": 2712.50,
            "downside_sweep_target": 2670.00
        },
        "macro_blackout_warning": "NO_NEWS_WITHIN_60M"
    }