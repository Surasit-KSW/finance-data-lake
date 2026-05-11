"""
api/index.py — Vercel Entry Point
Mangum wraps the FastAPI ASGI app for Vercel/Lambda serverless.
"""
import os
import sys
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

_app = FastAPI(title="Finance Data Lake API", version="1.0.0")

_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_errors: dict = {}

# Load routers
for _mod in ["health", "gl_detail", "audit_data", "cost_closing", "financial_tb"]:
    try:
        import importlib
        m = importlib.import_module(f"backend.routers.{_mod}")
        _app.include_router(m.router)
    except Exception:
        _errors[_mod] = traceback.format_exc()


@_app.get("/")
def root():
    return {
        "service": "Finance Data Lake API",
        "version": "1.0.0",
        "health": "/api/v1/health",
        "docs": "/docs",
        "db": "postgresql" if os.environ.get("DATABASE_URL") else "duckdb (local)",
        "startup_errors": _errors or None,
    }


# Vercel/Lambda handler — Mangum adapts ASGI → WSGI/Lambda
handler = Mangum(_app, lifespan="off")

# Also expose as 'app' for Vercel's ASGI auto-detection
app = _app
