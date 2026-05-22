# Finance Data Lake — Claude Context

> Claude Code reads this file automatically when you open this project.
> Last updated: 2026-05

---

## Project Purpose

Central data hub for Asia Metal (AMC) financial reporting. Provides a REST API
backed by **DuckDB** (local development) or **Neon PostgreSQL** (Vercel/cloud).

Raw SAP exports flow through a medallion ETL pipeline (Bronze → Silver → Gold),
then served to four downstream consumer projects via HTTP REST.

**This is a shared production API.** Changes to routers, services, or DuckDB schema
affect four external projects simultaneously.

---

## Key Commands

```bash
# Start local API (port 8000)
uvicorn backend.main:app --reload --port 8000

# Interactive API docs
# http://localhost:8000/docs

# Health check
curl http://localhost:8000/api/v1/health

# Run full ETL pipeline (Silver + Gold + DuckDB init)
python run_pipeline.py --all

# Specific domain only
python run_pipeline.py --layer silver --domain gl
python run_pipeline.py --layer silver --domain sales --year 2026
python run_pipeline.py --layer silver --domain production --year 2026
python run_pipeline.py --layer silver --domain ar

# DuckDB refresh only (after Parquet changes)
python run_pipeline.py --init-db

# Sync to Neon PostgreSQL (requires DATABASE_URL in .env)
python scripts/migrate_to_neon.py

# Open Streamlit audit dashboard
python run_pipeline.py --dashboard

# Test the shared lake_client
python 06_Scripts/utils/lake_client.py
```

See `/run-pipeline`, `/health-check`, `/start-api`, `/migrate-neon` for guided versions.

---

## Architecture

```
_Finance_Data_Lake/
│
├── 01_Bronze_Raw/            Raw SAP Excel exports — NOT in git, never modify
│   ├── GL_Transactions/      FBL3N  → sap_fbl3n.XLSX
│   ├── Sales_Reports/YYYY/   VF05   → sale_YYYY_MM.XLSX
│   ├── Production/YYYY/      MB52   → PLANT_YYYY_MM.XLSX (1100/1200/1300)
│   ├── AR_Data/              FBL5N  → AR_YYYY.XLSX
│   ├── Templates/            Leadsheet Excel templates
│   └── Inventory_RollStock/  NRV + TB Excel files
│
├── 02_Silver_Cleaned/        Cleaned Parquet — NOT in git
│   ├── master_sales_YYYY.parquet         (one per year, ~10 MB each)
│   ├── master_production_YYYY.parquet    (one per year)
│   ├── Master_GL_24_25.parquet           (~82 MB, combined 2024-2025)
│   └── master_ar.parquet
│
├── 03_Gold_DataMarts/        Aggregated Parquet — NOT in git
│   └── Summary_GL_24_25.parquet
│
├── 04_Data_Pipelines/        ETL scripts (Bronze → Silver → Gold → DuckDB)
│   ├── silver_transform/     etl_gl.py, etl_sales.py, etl_ar.py, etl_production.py
│   ├── gold_aggregation/     create_gold_summary.py + other Gold builders
│   └── init_duckdb.py        Creates DuckDB views from Parquet files
│
├── 05_Dashboards/            Streamlit apps
│
├── 06_Scripts/               Analysis + reporting scripts
│   ├── leadsheet/            Quarterly audit leadsheet builder (Q1'26 complete)
│   ├── audit/                AR, GL, Sales, Production audit analytics
│   ├── reporting/            NRV, production cost reporting
│   └── utils/
│       ├── lake_client.py    HTTP client — shared by all consumer projects
│       └── lake_config.py    Reads 08_Config/data_paths.yaml
│
├── 07_Workspace/             Google Sheets scripts (merged from _Finance workspace)
│   ├── reconcile/            GI recon Plant 1300/1100, format recon
│   ├── cost/                 MB51 breakdown, electricity alloc AMC/GA, GI templates
│   ├── monthend/             Month-end costing template generator
│   ├── analytics/            Analytics (trend, outlier, forecast) → Google Sheets
│   ├── utils/                gspread auth, Sheets I/O, Drive, finance calc
│   ├── config/settings.py    Workspace finance constants + Drive IDs
│   ├── 02_Working/           Local Excel outputs (git-ignored)
│   └── .credentials/         Google OAuth token (git-ignored)
│   NOTE: ข้อมูล SAP ใช้ร่วมกับ 01_Bronze_Raw/PRD_GI/ (ไม่ duplicate)
│
├── 08_Config/
│   ├── data_paths.yaml       Canonical path registry — source of truth for all paths
│   └── api_config.yaml       API configuration (ports, CORS)
│
├── api/
│   └── index.py              Vercel entry point (v1 routers only, no DuckDB startup)
│
├── backend/
│   ├── main.py               FastAPI app — includes all routers
│   ├── core/
│   │   ├── config.py         Pydantic settings — paths, API config, DATABASE_URL
│   │   └── database.py       DuckDB (read-only) + ops SQLite connections
│   ├── routers/              One file per domain
│   │   ├── health.py         GET /health  +  GET /api/v1/health
│   │   ├── financial_tb.py   GET /api/v1/financial/tb/{period}  (Excel or PostgreSQL)
│   │   ├── gl_detail.py      GET /api/v1/gl/transactions|balance|accounts
│   │   ├── audit_data.py     GET /api/v1/audit/ar-aging|ar-summary|gl-reconcile
│   │   ├── cost_closing.py   GET /api/v1/cost-closing/zreport|production-cost|fi-co-diff
│   │   ├── sales.py          GET /api/sales/summary/{year}   (legacy)
│   │   ├── ar.py             GET /api/ar/summary             (legacy)
│   │   ├── lake.py           GET /api/lake/status
│   │   ├── etl.py            POST /api/etl/run
│   │   ├── finance.py        Legacy financial endpoints
│   │   └── reports.py        Legacy reports endpoints
│   └── services/
│       ├── db_service.py     Unified query — routes DuckDB (local) or PostgreSQL (cloud)
│       ├── duck_service.py   DuckDB-specific query helpers
│       ├── etl_service.py    ETL run tracking (operations.db)
│       └── finance_calc.py   Financial calculation helpers
│
├── scripts/
│   ├── setup_neon_schema.sql PostgreSQL DDL — run once at cloud setup
│   └── migrate_to_neon.py    Loads Silver/Gold Parquet into Neon (monthly)
│
├── finance_lake.duckdb       Local DuckDB — NOT in git (rebuilt via init_duckdb.py)
├── operations.db             ETL run history — NOT in git
├── run_pipeline.py           Master pipeline runner (entry point for all ETL)
├── vercel.json               Vercel build config (routes all → api/index.py)
├── .gitignore                Excludes all data files (Parquet, Excel, .duckdb, .env)
├── requirements.txt          Full local dev deps (DuckDB, Streamlit, psycopg2, etc.)
└── api/requirements.txt      Vercel-only deps — no DuckDB, no Streamlit
```

---

## Data Flow

```
SAP Export (Excel)
  [manual]            → 01_Bronze_Raw/         copy SAP export here, never modify
  [etl_*.py]          → 02_Silver_Cleaned/     typed + validated Parquet
  [create_gold_*.py]  → 03_Gold_DataMarts/     aggregated Parquet
  [init_duckdb.py]    → finance_lake.duckdb    DuckDB views (pointers to Parquet)
  [backend/main.py]   → REST API :8000         serves via DuckDB locally
  [migrate_to_neon]   → Neon PostgreSQL        cloud DB for Vercel deployment
```

**DB backend auto-detection** (in `db_service.py`):
- `DATABASE_URL` empty → DuckDB local
- `DATABASE_URL` set   → Neon PostgreSQL (Vercel)

---

## API Endpoint Reference

### Versioned `/api/v1/` — use these in new code

| Method | Path | Params | Description |
|--------|------|--------|-------------|
| GET | `/api/v1/health` | — | API status, DB backend, DuckDB views |
| GET | `/api/v1/financial/tb/{period}` | period: YYYY-MM-DD | Trial Balance |
| GET | `/api/v1/financial/tb` | — | List available TB periods |
| GET | `/api/v1/financial/master-tb` | — | Master TB account index |
| POST | `/api/v1/financial/leadsheet/build` | — | Trigger leadsheet build |
| GET | `/api/v1/gl/transactions` | year, month?, account?, limit | GL line items |
| GET | `/api/v1/gl/balance/{account}` | year? | Monthly cumulative balance |
| GET | `/api/v1/gl/accounts` | year, search? | All GL accounts with totals |
| GET | `/api/v1/audit/ar-aging` | as_of_year, as_of_month, customer? | AR aging |
| GET | `/api/v1/audit/ar-summary` | year | AR summary by customer |
| GET | `/api/v1/audit/gl-reconcile` | account, year | GL reconcile vs TB |
| GET | `/api/v1/cost-closing/zreport` | period? | Z-Report cost center |
| GET | `/api/v1/cost-closing/production-cost` | year, month?, plant? | Production cost |
| GET | `/api/v1/cost-closing/fi-co-diff` | period?, threshold? | FI-CO mismatch |

### Legacy `/api/` — keep working, do not remove

| GET | `/health` | — | Same as v1 health |
| GET | `/api/lake/status` | — | DuckDB view row counts |
| GET | `/api/sales/summary/{year}` | — | Monthly sales by product |
| POST | `/api/etl/run` | — | Trigger ETL (tracked in operations.db) |

Full interactive docs: http://localhost:8000/docs

---

## Consumer Projects

These projects connect to this API. Never remove or rename an endpoint they use.

| Project | Directory | Connection | Endpoints Used |
|---------|-----------|-----------|----------------|
| `audit-reconcile` | `../audit-reconcile/` | `lake_client.py` | `/api/v1/gl/*`, `/api/v1/audit/*` |
| `main-dashboard` | `../main-dashboard/` | Next.js HTTP | all v1 endpoints |
| `fin-dashboard` | `../fin-dashboard/` | Next.js HTTP | `/api/v1/financial/*`, `/api/v1/gl/*` |
| `sap_cost_closing_app` | `../sap_cost_closing_app/` | `lake_client.py` | `/api/v1/cost-closing/*` |

`cost_closing.py` also reads CSV files directly from `../sap_cost_closing_app/data/processed/` — that sibling path is hardcoded in the router.

---

## Critical Rules — Do NOT Do These

1. **Do not move this project directory.** `data_paths.yaml` hardcodes the absolute path. Vercel deployment references the current Git remote URL.

2. **Do not commit data files.** `01_Bronze_Raw/`, `02_Silver_Cleaned/*.parquet`, `03_Gold_DataMarts/*.parquet`, `*.duckdb`, `*.db`, `*.xlsx`, `.env` are all gitignored. They contain sensitive financial data.

3. **Do not remove legacy `/api/` endpoints.** The `/api/sales/`, `/api/ar/`, `/api/lake/`, `/api/etl/` routes are still consumed by older scripts. New endpoints go under `/api/v1/`, but legacy routes stay.

4. **Do not edit Bronze files.** `01_Bronze_Raw/` is read-only. All transformations happen in ETL scripts. If source data has errors, fix them in the ETL scripts, not in the Bronze files.

5. **Do not use `strftime()` in SQL.** Use `EXTRACT(YEAR FROM col)` and `EXTRACT(MONTH FROM col)` — compatible with both DuckDB and PostgreSQL. The `db_service.py` routes to either backend.

6. **Do not hardcode absolute paths in Python.** Use `settings.PROJECT_ROOT / "subdir"` (from `backend/core/config.py`) or `LakeConfig()` (from `06_Scripts/utils/lake_config.py`).

7. **Do not add DuckDB or Streamlit to `api/requirements.txt`.** That file is for Vercel — must stay minimal. DuckDB is local-only and cannot run on Vercel serverless.

---

## Current State and Known Issues (2026-05)

- **Dual router namespaces**: Legacy `/api/*` (duck_service only) and versioned `/api/v1/*` (db_service, PostgreSQL-compatible). New endpoints always go in `/api/v1/`.
- **`v_ar` view missing from DuckDB**: `init_duckdb.py` does not include a `v_ar` view yet. `master_ar.parquet` exists but needs to be added to the view map. The v1 AR endpoints work via `v_ar` table in PostgreSQL only.
- **`cost_closing.py` reads sibling project files**: `../sap_cost_closing_app/data/processed/` — these endpoints return 404 if that project's pipeline hasn't run.
- **`finance_lake.duckdb` must be rebuilt after any Parquet update**: Views are pointers. Re-run `python run_pipeline.py --init-db` after any ETL run.
- **Windows encoding**: All scripts include `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`. Do not remove these guards.
- **`financial_tb.py` reads Excel files on local, PostgreSQL on Vercel**: The router checks `settings.use_postgres` to switch source. Excel files (TB SAP export, YE25 leadsheet) must exist locally for local dev.

---

## Environment Variables

| Variable | Local dev | Vercel/Cloud |
|----------|-----------|-------------|
| `DATABASE_URL` | empty (uses DuckDB) | Neon PostgreSQL connection string |
| `DATA_LAKE_URL` | `http://localhost:8000` | `https://your-project.vercel.app` |

`.env` (never commit):
```
DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
```

---

## Deployment

- **Local**: `uvicorn backend.main:app --reload --port 8000`
- **Vercel**: auto-deploys from GitHub via `vercel.json` → entry point `api/index.py`
- **Cloud DB**: Neon PostgreSQL — run `scripts/migrate_to_neon.py` monthly after SAP refresh

---

## 07_Workspace — Finance Operations Scripts

สร้างจากการ merge `_Finance workspace` (2026-05-22)

### Quick Start
```bash
# Reconciliation Plant 1300
python 07_Workspace/reconcile/recon_gi_plant1300.py --month 3

# MB51 Cost Breakdown
python 07_Workspace/cost/mb51_cost_breakdown.py

# Electricity Allocation AMC
python 07_Workspace/cost/electricity_alloc_amc_v2.py

# Month-End Costing Template
python 07_Workspace/monthend/generate_monthend_costing_template.py --month 05 --year 2026
```

### Import Pattern
Scripts ใน `07_Workspace/` ใช้ `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`
เพื่อให้ `from utils.auth import ...` และ `from config.settings import ...` ทำงานได้

### Data Paths
- **SAP Input:** `01_Bronze_Raw/PRD_GI/` (shared กับ Data Lake pipeline)
- **Local Output:** `07_Workspace/02_Working/` (Excel files — git-ignored)
- **Google Sheets Output:** ผ่าน gspread (credentials: `07_Workspace/.credentials/token.json`)

### Environment Variables ที่ต้องการ
- `DRIVE_ROOT_ID`, `DRIVE_WORKING_ID`, etc. — Google Drive folder IDs
- `RECON_LOG_SHEET_ID`, `ANALYTICS_LOG_SHEET_ID` — audit log sheets

### Finance Rules (vault-derived)
- THB, ROUND(x,2), tolerance ±0.01, DD/MM/YYYY
- GL exclude: 5391020 (ML variance), 5211010 (Semi-FG)
- Outlier: mean ± 2σ; flag >500K

---

## Workspace Context

This project lives at `D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake\`.

Sibling projects that depend on it being at this exact location:
- `../audit-reconcile/`
- `../sap_cost_closing_app/`
- `../main-dashboard/`
- `../fin-dashboard/`
