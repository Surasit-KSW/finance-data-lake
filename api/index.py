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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings

# Cloud-optimised app — only v1 routers, no local-file dependencies
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=(
        "Finance Data Lake REST API — deployed on Vercel. "
        "Backed by Neon PostgreSQL when DATABASE_URL is set."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict per-domain in Vercel env if needed
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Import v1 routers ────────────────────────────────────────────────────────
from backend.routers import health
from backend.routers import financial_tb, gl_detail, audit_data, cost_closing, dashboard

app.include_router(health.router)
app.include_router(financial_tb.router)
app.include_router(gl_detail.router)
app.include_router(audit_data.router)
app.include_router(cost_closing.router)
app.include_router(dashboard.router)


@app.get("/")
def root():
    return {
        "service": "Finance Data Lake API",
        "version": settings.API_VERSION,
        "docs":    "/docs",
        "health":  "/api/v1/health",
        "db":      "postgresql" if settings.use_postgres else "duckdb (local)",
    }
