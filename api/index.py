"""
api/index.py — Vercel Entry Point
==================================
FastAPI app exposed to Vercel serverless runtime.

Local dev : uvicorn backend.main:app --reload --port 8000
Vercel    : auto-detected via vercel.json builds config

Environment variables (set in Vercel dashboard):
  DATABASE_URL = postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
  DATA_LAKE_URL = https://your-project.vercel.app   (for lake_client consumers)
"""
import os
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Finance Data Lake API", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load routers with error capture so startup failures are visible ──────────
_errors = {}

try:
    from backend.core.config import settings
    _settings_ok = True
except Exception as e:
    _settings_ok = False
    _errors["settings"] = str(e)

try:
    from backend.routers import health
    app.include_router(health.router)
except Exception as e:
    _errors["health"] = traceback.format_exc()

try:
    from backend.routers import financial_tb
    app.include_router(financial_tb.router)
except Exception as e:
    _errors["financial_tb"] = traceback.format_exc()

try:
    from backend.routers import gl_detail
    app.include_router(gl_detail.router)
except Exception as e:
    _errors["gl_detail"] = traceback.format_exc()

try:
    from backend.routers import audit_data
    app.include_router(audit_data.router)
except Exception as e:
    _errors["audit_data"] = traceback.format_exc()

try:
    from backend.routers import cost_closing
    app.include_router(cost_closing.router)
except Exception as e:
    _errors["cost_closing"] = traceback.format_exc()


@app.get("/")
def root():
    return {
        "service":  "Finance Data Lake API",
        "version":  "1.0.0",
        "docs":     "/docs",
        "health":   "/api/v1/health",
        "db":       "postgresql" if (os.environ.get("DATABASE_URL") or "") else "duckdb (local)",
        "startup_errors": _errors if _errors else None,
    }


@app.get("/api/v1/startup-check")
def startup_check():
    """Show which routers loaded successfully."""
    return {
        "settings_loaded": _settings_ok,
        "errors": _errors,
        "routes": [r.path for r in app.routes],
    }
