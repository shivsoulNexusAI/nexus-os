import os
import sys
from pathlib import Path
import uvicorn

# Enforce project root in PYTHONPATH
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

os.environ["PYTHONPATH"] = str(project_root)
os.environ.setdefault("NEXUS_ADMIN_KEY", "admin-secret-key-2026-secure")
os.environ.setdefault("NEXUS_OPERATOR_KEY", "operator-secret-key-2026-secure")

if __name__ == "__main__":
    print(f"[NEXUS OS] Starting production ASGI gateway on http://127.0.0.1:8000")
    print(f"[NEXUS OS] Working directory: {project_root}")
    uvicorn.run(
        "core.api:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )
