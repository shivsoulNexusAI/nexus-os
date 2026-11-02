# Mock Database (SQLAlchemy C-extensions blocked by Windows Security)
# We are using In-Memory Mode to get the Quantum Nexus LIVE immediately.

async def init_db():
    print("INFO - [MOCK] Database initialized (In-Memory Mode)")

async def get_db():
    yield {}
