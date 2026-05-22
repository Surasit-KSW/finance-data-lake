"""
Finance Data Lake — FastAPI Backend
รัน: uvicorn backend.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
import sys
import io

# UTF-8 output สำหรับ Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.database import init_ops_db
from backend.routers import health, lake, finance, sales, ar, etl, reports
from backend.routers import financial_tb, gl_detail, audit_data, cost_closing, dashboard

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=(
        "Finance Data Lake REST API — Central hub for all financial data. "
        "Serves Trial Balance, GL, Sales, AR, Audit, Cost Closing data "
        "to all connected projects (leadsheet, audit-reconcile, dashboards, sap_cost_closing)."
    ),
)

# CORS — restrict origins in production via settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Existing routers (legacy prefix /api) ────────────────────────────────
app.include_router(health.router)
app.include_router(lake.router)
app.include_router(finance.router)
app.include_router(sales.router)
app.include_router(ar.router)
app.include_router(etl.router)
app.include_router(reports.router)

# ── New versioned routers (/api/v1) ──────────────────────────────────────
app.include_router(financial_tb.router)   # /api/v1/financial/...
app.include_router(gl_detail.router)      # /api/v1/gl/...
app.include_router(audit_data.router)     # /api/v1/audit/...
app.include_router(cost_closing.router)   # /api/v1/cost-closing/...
app.include_router(dashboard.router)      # /api/v1/{financial-performance,liquidity,...}


@app.on_event("startup")
def on_startup():
    """สร้าง operations.db tables เมื่อ server เริ่มทำงาน"""
    init_ops_db()
    print(f"\n Finance Data Lake API ready")
    print(f"   DuckDB  : {settings.DUCK_DB}")
    print(f"   Ops DB  : {settings.OPS_DB}")
    print(f"   Docs    : http://localhost:8000/docs\n")
