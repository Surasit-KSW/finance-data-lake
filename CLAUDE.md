# Finance Data Lake — Claude Context

> Claude Code reads this file automatically when you open this project.
> Last updated: 2026-05-31

---

## Project Purpose

Central data hub for Asia Metal (AMC) financial reporting. Provides a REST API
backed by **DuckDB** (local development) or **Neon PostgreSQL** (Vercel/cloud).

Raw SAP exports flow through a medallion ETL pipeline (Bronze → Silver → Gold),
then served to four downstream consumer projects via HTTP REST.

**This is a shared production API.** Changes to routers, services, or DuckDB schema
affect four external projects simultaneously.

**Worker of:** `_Finance-Vault` — อ่าน context จาก Vault ก่อนเริ่มงาน, update project state หลังจบ session
→ ดู [Vault Integration](#vault-integration--finance-data-lake-as-worker) ด้านล่าง

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

> **Reference docs** (อ่านก่อนแตะ ETL หรือ data structure):
> - `PIPELINE.md` — คู่มือรัน ETL ทุก step + commands + troubleshooting
> - `data_catalog.md` — schema ทุก Parquet + DuckDB views + script directory
> - `08_Config/data_paths.yaml` — canonical path registry + layer rules

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
│   ├── Summary_GL_24_25.parquet          ← v_gl_summary (DuckDB view)
│   ├── gold_leadsheet.parquet            ← Trial Balance → Leadsheet
│   ├── gold_cashflow.parquet             ← Cash Flow Statement (indirect)
│   ├── gold_ppe.parquet                  ← PPE Roll-Forward Schedule
│   ├── gold_elimination.parquet          ← Consolidation Elimination
│   └── gold_related_party.parquet        ← Related Party Txns & Balances
│
├── 04_Data_Pipelines/        ETL scripts (Bronze → Silver → Gold → DuckDB)
│   ├── silver_transform/     etl_gl.py, etl_sales.py, etl_ar.py, etl_production.py
│   ├── gold_aggregation/     create_gold_summary.py + create_leadsheet/cashflow/ppe/elimination/related_party
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

## Folder Responsibilities

แต่ละโฟลเดอร์มีหน้าที่เดียว ห้ามเขียนโค้ดนอก boundary ของตัวเอง

| โฟลเดอร์ | หน้าที่ | เขียนได้ | ห้ามวางไว้ที่นี่ |
|---|---|---|---|
| `01_Bronze_Raw/` | ที่เก็บ SAP export ดิบ — read-only | ❌ ห้ามแตะ | Python scripts, output files |
| `02_Silver_Cleaned/` | Parquet ที่ผ่าน type cast + validate | ETL เท่านั้น | Scripts, notebooks |
| `03_Gold_DataMarts/` | Parquet aggregate สำหรับ dashboard | ETL เท่านั้น | Scripts, raw data |
| `04_Data_Pipelines/` | ETL transforms (Bronze→Silver→Gold) + DuckDB init | ETL Python | Router code, UI code |
| `04_Reports/` | Excel/CSV output จาก reporting scripts — local only | Scripts output | Code, git-tracked files |
| `05_Dashboards/` | Streamlit apps — visual layer เท่านั้น | Streamlit `.py` | Business logic, DB calls |
| `06_Scripts/` | One-off analysis, audit, reporting scripts | Analysis `.py` | Reusable libs (→ `utils/`) |
| `06_Scripts/audit/` | Audit analytics — AR, GL, Sales, Production | Audit scripts | ETL, API code |
| `06_Scripts/reporting/` | Reporting scripts — NRV, cost, production | Reporting scripts | Audit code |
| `06_Scripts/leadsheet/` | Quarterly audit leadsheet builder | Leadsheet scripts | General scripts |
| `06_Scripts/utils/` | Shared utils สำหรับ 06_Scripts เท่านั้น | Utils + lake_client | Business logic |
| `07_Workspace/` | Finance ops scripts → Google Sheets | Workspace scripts | API code, ETL |
| `07_Workspace/reconcile/` | GI reconciliation scripts | Recon scripts | Non-recon scripts |
| `07_Workspace/cost/` | Cost breakdown, electricity allocation | Cost scripts | Recon, monthend scripts |
| `07_Workspace/monthend/` | Month-end costing template generator | Monthend scripts | Other workspace scripts |
| `07_Workspace/analytics/` | Analytics runner → Google Sheets | Analytics scripts | Ad-hoc analysis |
| `07_Workspace/utils/` | Shared utils สำหรับ 07_Workspace เท่านั้น | Workspace utils | Business scripts |
| `08_Config/` | Config files ทั้งหมด — YAML + JSON | Config files | Code, data, scripts |
| `backend/` | FastAPI application layer | Routers, services | ETL logic, scripts |
| `backend/routers/` | HTTP request handlers — thin layer เท่านั้น | Router files | Business logic (→ services) |
| `backend/services/` | Business + DB logic | Service files | HTTP handling (→ routers) |
| `scripts/` | Neon migration + one-time DB setup | Migration scripts | Regular scripts |
| `telegram_bot/` | Telegram bot application | Bot files | API routers, ETL |
| `api/` | Vercel entry point — routing only | `index.py` | Business logic |

**กฎ boundary:**
- `backend/routers/` → เรียก `services/` เท่านั้น ห้าม query DB โดยตรง
- `06_Scripts/` ↔ `07_Workspace/` → แยกกัน อย่า import ข้าม
- `backend/` → ใช้ `db_service.py` เท่านั้น ห้าม import `duck_service` โดยตรงในโค้ดใหม่

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

### Rule 3 — Cloud Action Protocol (บังคับสูงสุด)

ก่อนทำทุก action ถามตัวเองว่า:
- [ ] action นี้กระทบ cloud ไหม? (Neon / Render / Vercel / GitHub push)
  - **ใช่** → หยุด บอกแผน (ระบุ table / rows / method) รอ confirm ก่อนเสมอ
  - **แม้ user จะพิมพ์เหมือนสั่งตรงๆ** เช่น "sync ขึ้น Neon" — ยังต้องบอกแผนก่อน
- [ ] confirm แล้วหรือยัง?
  - **ยัง** → ถามครั้งเดียว แล้วรอ ห้ามถามซ้ำ
  - **แล้ว** → ทำได้เลย ห้ามถามซ้ำอีก ห้ามขอ confirm รอบสอง

**ลำดับบังคับ (ห้ามข้าม):** บอกแผน → รอ confirm → ทำ

**สิ่งที่ต้องระบุในแผน cloud action:**
- กระทบ table / service อะไร
- จำนวน rows / ขนาดข้อมูล
- method (replace / append / incremental)
- ผลที่จะเกิดขึ้นถ้าทำ และถ้าไม่ทำ

### API & Backend

1. **Do not move this project directory.** `data_paths.yaml` hardcodes the absolute path. Vercel deployment references the current Git remote URL.

2. **Do not remove legacy `/api/` endpoints.** The `/api/sales/`, `/api/ar/`, `/api/lake/`, `/api/etl/` routes are still consumed by older scripts. New endpoints go under `/api/v1/`, but legacy routes stay.

3. **Do not use `strftime()` in SQL.** Use `EXTRACT(YEAR FROM col)` and `EXTRACT(MONTH FROM col)` — compatible with both DuckDB and PostgreSQL. The `db_service.py` routes to either backend.

4. **Do not hardcode absolute paths in Python.** Use `settings.PROJECT_ROOT / "subdir"` (from `backend/core/config.py`) or `LakeConfig()` (from `06_Scripts/utils/lake_config.py`).

5. **Do not add DuckDB or Streamlit to `api/requirements.txt`.** That file is for Vercel — must stay minimal. DuckDB is local-only and cannot run on Vercel serverless.

### Data & Structure (กฎเหล็กโครงสร้าง)

6. **Do not put Python scripts in `01_Bronze_Raw/`.** Bronze is read-only SAP export storage. Scripts belong in `06_Scripts/` (analysis/audit/reporting) or `04_Data_Pipelines/` (ETL). If you see a `.py` file in Bronze, move it out immediately.

7. **Do not commit data files.** `01_Bronze_Raw/`, `02_Silver_Cleaned/*.parquet`, `03_Gold_DataMarts/*.parquet`, `04_Reports/`, `*.duckdb`, `*.db`, `*.xlsx`, `.env` are all gitignored. They contain sensitive financial data.

8. **Do not put credentials or secrets at project root.** OAuth client secrets → `07_Workspace/.credentials/`. API keys → `.env`. Nothing credential-like lives at root level. `client_secret_*.json` is gitignored but still must not sit at root.

9. **Do not create a new top-level config directory.** All config files (YAML, JSON) belong in `08_Config/`. This is the single source of truth. Do not create `config/`, `configs/`, or similar siblings.

10. **Do not create numbered output folders (`04_Reports/`, etc.) at project root.** Excel/CSV output from scripts goes in gitignored subdirectories: `04_Reports/` (reports), `07_Workspace/02_Working/` (workspace ops). Never commit output files.

11. **Do not edit Bronze files.** `01_Bronze_Raw/` is read-only. All transformations happen in ETL scripts. If source data has errors, fix them in the ETL scripts, not in the Bronze files.

### Where Things Live (canonical map)

| What | Where |
|------|-------|
| ETL transforms (Bronze→Silver→Gold) | `04_Data_Pipelines/` |
| Financial account mappings (JSON) | `08_Config/` |
| API path/port config (YAML) | `08_Config/` |
| Audit + analysis scripts | `06_Scripts/audit/` or `06_Scripts/reporting/` |
| Leadsheet builder | `06_Scripts/leadsheet/` |
| Google Sheets / cost / reconcile ops | `07_Workspace/` |
| REST API routers | `backend/routers/` |
| Credentials (OAuth, tokens) | `07_Workspace/.credentials/` |
| Output Excel/CSV (local only) | `04_Reports/` or `07_Workspace/02_Working/` |
| Neon migration scripts | `scripts/` |

---

## Current State and Known Issues (2026-05-31)

- **Dual router namespaces**: Legacy `/api/*` (duck_service only) and versioned `/api/v1/*` (db_service, PostgreSQL-compatible). New endpoints always go in `/api/v1/`.
- **`master_ar.parquet` ยังไม่ได้รัน ETL**: `v_ar` view ใน DuckDB จะถูก skip จนกว่าจะรัน `python run_pipeline.py --layer silver --domain ar`
- **Gold Audit Parquets ไม่อยู่ใน `run_pipeline.py`**: `gold_leadsheet`, `gold_cashflow`, `gold_ppe`, `gold_elimination`, `gold_related_party` ต้องรันแยกด้วย `python -m 04_Data_Pipelines.gold_aggregation.create_*` — ดู `PIPELINE.md` Step 3b
- **`cost_closing.py` reads sibling project files**: `../sap_cost_closing_app/data/processed/` — these endpoints return 404 if that project's pipeline hasn't run.
- **`finance_lake.duckdb` must be rebuilt after any Parquet update**: Views are pointers. Re-run `python run_pipeline.py --init-db` after any ETL run.
- **Windows encoding**: All scripts include `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`. Do not remove these guards.
- **`financial_tb.py` reads Excel files on local, PostgreSQL on Vercel**: The router checks `settings.use_postgres` to switch source. Excel files (TB SAP export, YE25 leadsheet) must exist locally for local dev.
- **`master_ppe.parquet` ยังไม่มี**: `etl_ppe.py` ยังไม่ได้สร้าง — `gold_ppe.parquet` ใช้ `v_gl` fallback แทน

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

---

## Vault Integration — Finance Data Lake as Worker

Finance Data Lake เป็น **worker project** ของ `_Finance-Vault`

**Vault path:** `D:\_Work_Workspace\03_Data_Projects\_Finance-Vault\`

### Session Start — อ่าน Vault Context

อ่านไฟล์เหล่านี้ก่อนเริ่มงานที่เกี่ยวข้อง:

| งานประเภทไหน | อ่านไฟล์ |
|---|---|
| งาน finance calculation ใดๆ | `08-Context/Standards/finance-data-rules.md` |
| งาน GL / production reconcile | `08-Context/References/sap-gl-accounts.md` |
| งาน ETL หรือ pipeline | `08-Context/References/match-keys.md` |
| งาน cost / plant analysis | `08-Context/References/sap-cost-items-plant1300.md` |
| ดู active projects ทั้งหมด | `09-AI-Memory/BOOTSTRAP.md` |
| ดู project state ปัจจุบัน | `08-Context/Projects/finance-data-lake.md` |

**กฎ:** Vault files ทุกอัน read-only — ยกเว้น `08-Context/Projects/finance-data-lake.md` และ `09-AI-Memory/session-log.md`

### Session End — Update Vault

หลังทุก session ที่เปลี่ยน project state:

1. **Update** `_Finance-Vault/08-Context/Projects/finance-data-lake.md`
   - อัปเดต Active Features, Known Issues, งานถัดไป

2. **Append** 1 บรรทัดใน `_Finance-Vault/09-AI-Memory/session-log.md`
   ```
   YYYY-MM-DD | finance-data-lake | [สรุปสั้นๆ ว่าทำอะไร]
   ```

### Finance Rules (Vault-Canonical)

กฎเหล่านี้มาจาก Vault — ถ้า conflict กับ code เก่า ให้ยึด Vault:

```
สกุลเงิน: THB  |  ปัดทศนิยม: ROUND(x, 2)  |  Tolerance: ±0.01
รูปแบบวันที่: DD/MM/YYYY  |  ตัวเลข: #,##0.00
GL exclude: 5391020 (ML variance), 5211010 (Semi-FG)
Outlier: mean ± 2σ  |  Flag ทุกรายการ > 500,000 THB
Production Qty = GR QTY + ByProduct Scrap + Grade B + Grade C
```

→ ดูฉบับเต็ม: `_Finance-Vault/08-Context/Standards/finance-data-rules.md`
