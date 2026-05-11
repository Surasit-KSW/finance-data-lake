"""
api/index.py — Vercel Entry Point (diagnostic minimal version)
"""
import os
import sys
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Finance Data Lake API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_errors: dict = {}

# Step 1: try settings
try:
    from backend.core.config import settings
    _cfg = {"ok": True, "root": str(settings.PROJECT_ROOT)}
except Exception:
    _cfg = {"ok": False, "tb": traceback.format_exc()}
    _errors["config"] = _cfg["tb"]

# Step 2: try each router independently
for _mod in ["health", "gl_detail", "audit_data", "cost_closing", "financial_tb"]:
    try:
        import importlib
        m = importlib.import_module(f"backend.routers.{_mod}")
        app.include_router(m.router)
        _errors[_mod] = "ok"
    except Exception:
        _errors[_mod] = traceback.format_exc()


@app.get("/")
def root():
    return {
        "status": "ok",
        "python": sys.version,
        "config": _cfg,
        "routers": _errors,
    }


@app.get("/ping")
def ping():
    return {"pong": True}


@app.get("/api/v1/health")
def health_simple():
    db = "postgresql" if os.environ.get("DATABASE_URL") else "none"
    return {"status": "ok", "db": db, "routers": _errors}
