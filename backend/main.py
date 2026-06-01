"""
Finance Data Lake — FastAPI Backend
รัน local: uvicorn backend.main:app --reload --port 8000
Docs:       http://localhost:8000/docs
Deploy:     Railway — set DATABASE_URL env var → switches to Neon PostgreSQL
"""
import sys

# UTF-8 output สำหรับ Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.database import init_ops_db
from backend.routers import health, lake, finance, sales, ar, etl, reports
from backend.routers import financial_tb, gl_detail, audit_data, cost_closing, dashboard
from backend.routers import monitor, simulation

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=(
        "Finance Data Lake REST API — Central hub for all financial data. "
        "Serves GL, Sales, AR, Simulation, Monitor, Audit, Cost Closing data "
        "to fintech-command-center and other connected projects."
    ),
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Production: only Vercel frontend + localhost dev
# Never use wildcard '*' (data security)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── API Key middleware (production only) ──────────────────────────────────────
# Set API_KEY env var on Railway to require key on all requests.
# Local dev: API_KEY empty → no key required.
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # Skip auth for docs, health, and OPTIONS (CORS preflight)
    open_paths = {"/docs", "/openapi.json", "/redoc", "/health", "/api/v1/health"}
    if (
        not settings.API_KEY
        or request.method == "OPTIONS"
        or request.url.path in open_paths
    ):
        return await call_next(request)

    key = request.headers.get("X-API-Key", "")
    if key != settings.API_KEY:
        return JSONResponse(status_code=403, content={"detail": "Invalid or missing API key"})

    return await call_next(request)


# ── Legacy routers (prefix /api) ─────────────────────────────────────────────
app.include_router(health.router)
app.include_router(lake.router)
app.include_router(finance.router)
app.include_router(sales.router)
app.include_router(ar.router)
app.include_router(etl.router)
app.include_router(reports.router)

# ── Versioned routers (/api/v1) ───────────────────────────────────────────────
app.include_router(financial_tb.router)   # /api/v1/financial/...
app.include_router(gl_detail.router)      # /api/v1/gl/...
app.include_router(audit_data.router)     # /api/v1/audit/...
app.include_router(cost_closing.router)   # /api/v1/cost-closing/...
app.include_router(dashboard.router)      # /api/v1/{financial-performance,liquidity,...}
app.include_router(monitor.router)        # /api/v1/monitor/...
app.include_router(simulation.router)     # /api/v1/simulate/...


@app.on_event("startup")
def on_startup():
    init_ops_db()
    mode = "PRODUCTION (Neon PostgreSQL)" if settings.is_production else "LOCAL (DuckDB)"
    print(f"\n Finance Data Lake API ready — {mode}")
    if not settings.is_production:
        print(f"   DuckDB  : {settings.DUCK_DB}")
    print(f"   Docs    : http://localhost:8000/docs\n")
