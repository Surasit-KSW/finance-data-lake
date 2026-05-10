# Finance Data Lake

Central data hub for Asia Metal financial data.
REST API backed by DuckDB (local dev) or Neon PostgreSQL (Vercel/cloud).

## Architecture

```
01_Bronze_Raw/          Raw SAP exports (Excel) — NOT in git
02_Silver_Cleaned/      Cleaned Parquet files   — NOT in git
03_Gold_DataMarts/      Aggregated Parquet       — NOT in git
04_Data_Pipelines/      ETL scripts (Bronze -> Silver -> Gold)
05_Dashboards/          Streamlit dashboards
06_Scripts/             Analysis + Leadsheet builder
  utils/lake_client.py  HTTP client for external projects
08_Config/              Shared config (data_paths.yaml)
backend/                FastAPI application
  core/config.py        Settings (env-based, cloud-ready)
  routers/              REST endpoints (/api/v1/...)
  services/db_service.py  Unified query: DuckDB or PostgreSQL
scripts/                One-time setup scripts
  setup_neon_schema.sql PostgreSQL DDL
  migrate_to_neon.py    Load Parquet data into Neon
api/
  index.py              Vercel entry point
  requirements.txt      Vercel-specific deps (no DuckDB/Streamlit)
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/health` | DB status, API version |
| `GET /api/v1/financial/tb/{period}` | Trial Balance (YYYY-MM-DD) |
| `GET /api/v1/financial/master-tb` | Master TB account index |
| `GET /api/v1/gl/transactions?year=2025` | GL line items |
| `GET /api/v1/gl/balance/{account}` | Account balance by month |
| `GET /api/v1/gl/accounts?year=2025` | All GL accounts |
| `GET /api/v1/audit/ar-aging` | AR aging buckets |
| `GET /api/v1/cost-closing/production-cost` | Production cost |
| `GET /api/v1/cost-closing/zreport` | Z-Report (cost center) |

Docs: `http://localhost:8000/docs` (local) or `https://your-app.vercel.app/docs` (cloud)

---

## Local Development

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Initialize DuckDB views (reads Parquet files)
python 04_Data_Pipelines/init_duckdb.py

# 3. Start API
uvicorn backend.main:app --reload --port 8000

# 4. Test
curl http://localhost:8000/api/v1/health
```

---

## Deploy to Vercel (Production)

### Step 1 — Create Neon Database

1. Go to [neon.tech](https://neon.tech) → Sign up free
2. Create project: `finance-data-lake`
3. Copy connection string:
   ```
   postgresql://user:pass@ep-xxx-yyy.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

### Step 2 — Create PostgreSQL Schema

```bash
# Install psql if needed, then run:
psql "$DATABASE_URL" -f scripts/setup_neon_schema.sql
```

### Step 3 — Migrate Data to Neon

```bash
# Set DATABASE_URL in .env (never commit this file)
echo 'DATABASE_URL=postgresql://...' >> .env

# Run migration (loads Silver Parquet + TB Excel into Neon)
pip install psycopg2-binary python-dotenv
python scripts/migrate_to_neon.py
```

### Step 4 — Push to GitHub

```bash
git init   # if not already a git repo
git add .
git commit -m "feat: Finance Data Lake API"
git remote add origin https://github.com/your-username/finance-data-lake.git
git push -u origin main
```

### Step 5 — Deploy on Vercel

1. Go to [vercel.com](https://vercel.com) → New Project
2. Import from GitHub
3. **Add Environment Variables** in Vercel dashboard:
   ```
   DATABASE_URL = postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
   ```
4. Deploy!

Your API will be live at: `https://finance-data-lake.vercel.app`

---

## Environment Variables

| Variable | Local | Vercel |
|----------|-------|--------|
| `DATABASE_URL` | empty (uses DuckDB) | Neon PostgreSQL connection string |
| `DATA_LAKE_URL` | `http://localhost:8000` | `https://your-app.vercel.app` |

`.env` example (never commit):
```env
DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
```

---

## Re-syncing Data

When Silver Parquet files are updated (after running ETL pipeline), re-run migration:

```bash
python scripts/migrate_to_neon.py
```

This truncates and reloads all tables. Run monthly after SAP data refresh.

---

## Connected Projects

These projects consume the Data Lake API via `lake_client.py`:

| Project | Endpoints Used |
|---------|---------------|
| `audit-reconcile` | `/api/v1/gl/*`, `/api/v1/audit/*` |
| `main-dashboard` | all endpoints |
| `fin-dashboard` | `/api/v1/financial/*`, `/api/v1/gl/*` |
| `sap_cost_closing_app` | `/api/v1/cost-closing/*` |

```python
# Any Python project can import the client:
from lake_client import LakeClient
lake = LakeClient()  # reads DATA_LAKE_URL env var
df = lake.get_trial_balance("2026-03-31")
```
