# Finance Data Lake — Data Pipeline Reference

Monthly SAP data refresh guide. Run from the project root:
`D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake\`

---

## Overview

```
SAP Export (Excel)
  [manual]                → 01_Bronze_Raw/          Step 1: File drop
  [run_pipeline.py silver]→ 02_Silver_Cleaned/      Step 2: ETL Silver
  [run_pipeline.py gold]  → 03_Gold_DataMarts/      Step 3: ETL Gold
  [run_pipeline.py --init-db] → finance_lake.duckdb Step 4: DuckDB views
  [uvicorn]               → REST API :8000           Step 5: Serve locally
  [migrate_to_neon.py]    → Neon PostgreSQL          Step 6: Sync cloud
```

---

## Step 1 — Drop New SAP Exports into Bronze Layer

**Where to put which file:**

| SAP Transaction | SAP Menu | Local Folder | File Naming |
|----------------|----------|-------------|-------------|
| FBL3N (GL Detail) | Finance → GL → Line Items | `01_Bronze_Raw/GL_Transactions/` | `sap_fbl3n.XLSX` (replace in-place) |
| FBL5N (AR Open Items) | Finance → AR → Line Items | `01_Bronze_Raw/AR_Data/` | `AR_YYYY.XLSX` |
| VF05 / SD Sales | Sales → Billing | `01_Bronze_Raw/Sales_Reports/YYYY/` | `sale_YYYY_MM.XLSX` |
| MB52 / Production | MM → Inventory → Reports | `01_Bronze_Raw/Production/YYYY/` | `PLANT_YYYY_MM.XLSX` |
| Trial Balance (ZFI_TB) | — | `01_Bronze_Raw/Inventory_RollStock/NRV/` | `AMC_TB_MM.YYYY_vN.XLSX` |
| Templates / Leadsheet | — | `01_Bronze_Raw/Templates/` | Keep SAP original filename |

**Rules:**
- Never rename or edit Bronze files — they are source-of-truth
- GL: replace `sap_fbl3n.XLSX` entirely (ETL reads all files in the folder)
- Sales + Production: add the new monthly file; existing files are kept
- AR: add `AR_YYYY.XLSX` for the new year if it doesn't exist

**Verify Step 1:**
```bash
ls 01_Bronze_Raw/GL_Transactions/
ls "01_Bronze_Raw/Sales_Reports/2026/"
ls "01_Bronze_Raw/Production/2026/"
```

---

## Step 2 — Silver ETL (Bronze → Cleaned Parquet)

Silver scripts clean, type-cast, and consolidate raw Excel into Parquet format.

### Run all Silver transforms:
```bash
python run_pipeline.py --layer silver
```

### Or run a specific domain only:
```bash
python run_pipeline.py --layer silver --domain gl
python run_pipeline.py --layer silver --domain sales --year 2026
python run_pipeline.py --layer silver --domain production --year 2026
python run_pipeline.py --layer silver --domain ar
```

**What each script produces:**

| Script | Source | Output |
|--------|--------|--------|
| `etl_gl.py` | `01_Bronze_Raw/GL_Transactions/*.XLSX` | `02_Silver_Cleaned/Master_GL_24_25.parquet` |
| `etl_sales.py --year YYYY` | `01_Bronze_Raw/Sales_Reports/YYYY/*.XLSX` | `02_Silver_Cleaned/master_sales_YYYY.parquet` |
| `etl_production.py --year YYYY` | `01_Bronze_Raw/Production/YYYY/*.XLSX` | `02_Silver_Cleaned/master_production_YYYY.parquet` |
| `etl_ar.py` | `01_Bronze_Raw/AR_Data/*.XLSX` | `02_Silver_Cleaned/master_ar.parquet` |

**Verify Step 2:**
```bash
python -c "
import pandas as pd, os, glob
for f in sorted(glob.glob('02_Silver_Cleaned/*.parquet')):
    df = pd.read_parquet(f)
    print(f'{os.path.basename(f):45s} {len(df):>10,} rows')
"
```
Expected: each Parquet shows row counts. A new GL export should increase row count.

---

## Step 3 — Gold Aggregation (Silver → Aggregated Parquet)

Gold scripts aggregate Silver data into dashboard-ready summaries.

```bash
python run_pipeline.py --layer gold
```

**What it produces:**

| Script | Source | Output |
|--------|--------|--------|
| `create_gold_summary.py` | `02_Silver_Cleaned/Master_GL_24_25.parquet` | `03_Gold_DataMarts/Summary_GL_24_25.parquet` |

**Verify Step 3:**
```bash
python -c "
import pandas as pd
df = pd.read_parquet('03_Gold_DataMarts/Summary_GL_24_25.parquet')
print('Gold GL Summary:', len(df), 'rows')
print(df.groupby('Year')['Net_Amount'].sum().to_string())
"
```

---

## Step 4 — Initialize DuckDB Views

Creates or refreshes all DuckDB views pointing at the updated Parquet files.

```bash
python run_pipeline.py --init-db
# or directly:
python 04_Data_Pipelines/init_duckdb.py
```

**Views created in `finance_lake.duckdb`:**

| View | Source Parquet |
|------|---------------|
| `v_gl` | `Master_GL_24_25.parquet` |
| `v_gl_summary` | `Summary_GL_24_25.parquet` |
| `v_sales` | `master_sales_*.parquet` (wildcard, all years) |
| `v_sales_2023` | `master_sales_2023.parquet` |
| `v_sales_2024` | `master_sales_2024.parquet` |
| `v_sales_2025` | `master_sales_2025.parquet` |
| `v_production` | `master_production_*.parquet` (wildcard) |
| `v_production_2023..2025` | single-year production views |

**Verify Step 4:**
```bash
python -c "
import duckdb
con = duckdb.connect('finance_lake.duckdb')
views = con.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name\").fetchall()
for (v,) in views: print(' -', v)
con.close()
"
```

---

## Step 5 — Start / Restart the API

After updating DuckDB, restart the FastAPI server to pick up new data.

```bash
# Stop any running process first (Ctrl+C)
uvicorn backend.main:app --reload --port 8000
```

**Verify Step 5:**
```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status": "ok", "duckdb_views": [...], ...}

curl "http://localhost:8000/api/v1/gl/transactions?year=2026&limit=3"
```

Interactive docs: http://localhost:8000/docs

---

## Step 6 — Sync to Neon PostgreSQL (Cloud)

Push updated data to the cloud database for Vercel deployment.

**Prerequisites:**
```bash
# Verify DATABASE_URL is set in .env
python -c "
from dotenv import load_dotenv; import os
load_dotenv()
url = os.environ.get('DATABASE_URL','')
print('OK:', url[:40]+'...' if url else 'NOT SET - add to .env')
"
```

**Run migration** (safe to run multiple times — truncates and reloads):
```bash
python scripts/migrate_to_neon.py
```

**Verify cloud API:**
```bash
curl https://your-app.vercel.app/api/v1/health
```

---

## Full Monthly Refresh (All Steps)

```bash
# 1. Drop new SAP files into 01_Bronze_Raw/ (manual)

# 2-4. Run ETL + DuckDB in one command:
python run_pipeline.py --all

# 5. Restart local API
uvicorn backend.main:app --reload --port 8000

# 6. Sync to cloud
python scripts/migrate_to_neon.py
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| ETL exits with "ไม่พบไฟล์" | Bronze file missing or wrong name | Check folder + verify filename pattern |
| DuckDB views empty after `--init-db` | Silver Parquet not generated | Run `--layer silver` first |
| API returns `{"status": "degraded"}` | DuckDB missing or views stale | `python run_pipeline.py --init-db` |
| Silver row count lower than expected | New month file not in Bronze | Verify `01_Bronze_Raw/Sales_Reports/YYYY/` has new file |
| `migrate_to_neon.py` fails auth error | `DATABASE_URL` not set | Check `.env` file |
| `/api/v1/cost-closing/*` returns 404 | `sap_cost_closing_app/data/processed/` missing | Run cost closing pipeline in that project |
| `finance_lake.duckdb` not found | DuckDB never initialized | `python run_pipeline.py --init-db` |
| API returns old data after ETL | Old DuckDB process using cached views | Restart `uvicorn` |

---

## Adding a New Fiscal Year

When starting data for a new year (e.g., 2027):

1. **Create Bronze folders:**
   ```bash
   mkdir "01_Bronze_Raw/Sales_Reports/2027"
   mkdir "01_Bronze_Raw/Production/2027"
   ```

2. **Add DuckDB year-specific views** — edit `04_Data_Pipelines/init_duckdb.py`:
   ```python
   YEAR_VIEWS = {
       ...
       "v_sales_2027":      os.path.join(SILVER, "master_sales_2027.parquet"),
       "v_production_2027": os.path.join(SILVER, "master_production_2027.parquet"),
   }
   ```

3. **Add TB period** — edit `backend/routers/financial_tb.py`:
   ```python
   TB_FILES = {
       "2027-03-31": NRV_DIR / "AMC_TB_03.2027_vN.XLSX",
       "2026-12-31": ...,
       ...
   }
   ```

4. **Update data_paths.yaml** — add new year patterns in `08_Config/data_paths.yaml`

5. Re-run `python run_pipeline.py --all`

---

## Initial Cloud Setup (First Time Only)

Run these once to set up the Neon PostgreSQL database:

```bash
# 1. Create free Neon DB at https://neon.tech
#    Copy connection string to .env as DATABASE_URL

# 2. Create schema (run once)
psql "$DATABASE_URL" -f scripts/setup_neon_schema.sql

# 3. Load initial data
python scripts/migrate_to_neon.py

# 4. Set DATABASE_URL in Vercel dashboard
#    Vercel → Project → Settings → Environment Variables
```
