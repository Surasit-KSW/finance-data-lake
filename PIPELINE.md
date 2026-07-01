# Finance Data Lake — Data Pipeline Reference

อัพเดตล่าสุด: 2026-05-31
Monthly SAP data refresh guide. Run from the project root:
`D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake\`

---

## Overview

```
SAP Export (Excel)
  [manual]                          → 01_Bronze_Raw/          Step 1: File drop
  [orchestrator.py --layer silver]  → 02_Silver_Cleaned/      Step 2: ETL Silver
  [orchestrator.py --layer gold]    → 03_Gold_DataMarts/      Step 3a: GL Summary only
  [orchestrator.py --include-gold]  → 03_Gold_DataMarts/      Step 3b: Audit Gold Parquets (automated)
  [orchestrator.py --init-db]       → finance_lake.duckdb     Step 4: DuckDB views
  [uvicorn]                         → REST API :8000           Step 5: Serve locally
  [migrate_to_neon.py]              → Neon PostgreSQL          Step 6: Sync cloud
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
| KSB1 / Month-end CO | CO → Cost Centers | `01_Bronze_Raw/monthend/` | `GA_{CCTR}_*.XLSX` |
| KS13 Master data | CO → Master Data | `01_Bronze_Raw/Master/` | `KS13_Master.XLSX` (replace) |
| MB51 / PRD GI | MM → Goods Issue | `01_Bronze_Raw/PRD_GI/` | ตาม plant convention |

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
python orchestrator.py --layer silver
# (run_pipeline.py --layer silver also works — forwards to orchestrator automatically)
```

### Run a specific domain only:
```bash
python orchestrator.py --layer silver --domain gl
python orchestrator.py --layer silver --domain sales --year 2026
python orchestrator.py --layer silver --domain production --year 2026
python orchestrator.py --layer silver --domain ar
```

**What each script produces:**

| Script | Source | Output |
|--------|--------|--------|
| `etl_gl.py` | `01_Bronze_Raw/GL_Transactions/*.XLSX` | `02_Silver_Cleaned/master_gl_1000.parquet` |
| `etl_sales.py --year YYYY` | `01_Bronze_Raw/Sales_Reports/YYYY/*.XLSX` | `02_Silver_Cleaned/master_sales_1000.parquet` |
| `etl_production.py --year YYYY` | `01_Bronze_Raw/Production/YYYY/*.XLSX` | `02_Silver_Cleaned/master_production_1000.parquet` |
| `etl_ar.py` | `01_Bronze_Raw/AR_Data/*.XLSX` | `02_Silver_Cleaned/master_ar_1000.parquet` *(ยังไม่มีไฟล์)* |

**Verify Step 2:**
```bash
python -c "
import pandas as pd, os, glob
for f in sorted(glob.glob('02_Silver_Cleaned/*.parquet')):
    df = pd.read_parquet(f)
    print(f'{os.path.basename(f):45s} {len(df):>10,} rows')
"
```

---

## Step 3a — Gold ETL: GL Summary (via orchestrator.py)

`--layer gold` รันเฉพาะ **GL Summary** เท่านั้น — ใช้สำหรับ API dashboard

```bash
python orchestrator.py --layer gold
# (run_pipeline.py --layer gold also works — forwards to orchestrator automatically)
```

| Script | Source | Output |
|--------|--------|--------|
| `create_gold_summary.py` | `v_gl` (Silver GL) | `03_Gold_DataMarts/Summary_GL_24_25.parquet` |

**Verify:**
```bash
python -c "
import pandas as pd
df = pd.read_parquet('03_Gold_DataMarts/Summary_GL_24_25.parquet')
print('Gold GL Summary:', len(df), 'rows')
print(df.groupby('Year')['Net_Amount'].sum().to_string())
"
```

---

## Step 3b — Gold ETL: Audit Parquets (automated via orchestrator.py)

Gold Parquets สำหรับ audit/financial statements สามารถรันอัตโนมัติผ่าน orchestrator.py แล้ว:

```bash
# Silver + GL Summary + ทุก Gold Parquets + init-db ในคำสั่งเดียว:
python orchestrator.py --all --include-gold

# Gold scripts เท่านั้น (ใช้เมื่อ Silver เป็นปัจจุบันแล้ว):
# python orchestrator.py --gold-only   ← coming in Wave 2
```

หรือรันแยกทีละ script ตาม dependency ลำดับนี้:

**ลำดับ dependency:**
```
create_leadsheet.py        ← รันก่อน (ไม่มี dependency)
create_cashflow.py         ← ต้องมี gold_leadsheet.parquet ก่อน
create_ppe_schedule.py     ← ต้องมี v_gl (หรือ master_ppe.parquet)
create_elimination.py      ← ต้องมี gold_leadsheet.parquet ก่อน
create_related_party.py    ← ต้องมี v_gl
```

```bash
# 1. Leadsheet (รันก่อนเสมอ)
python -m 04_Data_Pipelines.gold_aggregation.create_leadsheet --year 2025 --quarter Q1

# 2. Cash Flow (ต้องมี leadsheet ก่อน)
python -m 04_Data_Pipelines.gold_aggregation.create_cashflow --year 2025 --quarter Q1

# 3. PPE Schedule
python -m 04_Data_Pipelines.gold_aggregation.create_ppe_schedule --year 2025 --quarter Q1

# 4. Elimination
python -m 04_Data_Pipelines.gold_aggregation.create_elimination --year 2025 --quarter Q1

# 5. Related Party
python -m 04_Data_Pipelines.gold_aggregation.create_related_party --year 2025 --quarter Q1
```

**Output ทั้งหมด → `03_Gold_DataMarts/`:**

| Output | คำอธิบาย |
|--------|---------|
| `gold_leadsheet.parquet` | Trial Balance → Leadsheet งบเดี่ยว/งบรวม |
| `gold_cashflow.parquet` | Cash Flow Statement (indirect method) |
| `gold_ppe.parquet` | PPE Roll-Forward Schedule |
| `gold_elimination.parquet` | Consolidation Elimination Entries |
| `gold_related_party.parquet` | Related Party Transactions & Balances |

> **Note:** Gold Parquets เหล่านี้มี DuckDB view (gold_leadsheet, gold_cashflow, gold_ppe, gold_elimination, gold_related_party) — ดู Step 4

---

## Step 4 — Initialize DuckDB Views

Creates or refreshes all DuckDB views pointing at the updated Parquet files.

```bash
python orchestrator.py --init-db
# (run_pipeline.py --init-db also works — forwards to orchestrator automatically)
# or directly:
python 04_Data_Pipelines/init_duckdb.py
```

**Views ที่สร้างใน `finance_lake.duckdb`:**

| View | Source Parquet | หมายเหตุ |
|------|---------------|---------|
| `v_gl` | `master_gl_1000.parquet` | GL transactions (company 1000) |
| `v_gl_summary` | `Summary_GL_24_25.parquet` | GL summary (Gold) |
| `v_sales` | `master_sales_1000.parquet` | Sales (company 1000) |
| `v_production` | `master_production_1000.parquet` | Production (company 1000) |
| `v_ar` | `master_ar_1000.parquet` | ⚠️ ข้ามถ้าไม่มีไฟล์ |
| `v_mb51` | `master_mb51_*.parquet` | MB51 material cost orders (standalone ETL) |
| `v_prd` | `master_prd_*.parquet` | Production daily log (standalone ETL) |
| `gold_leadsheet` | `gold_leadsheet.parquet` | Audit leadsheet P&L+BS |
| `gold_cashflow` | `gold_cashflow.parquet` | Cash flow (indirect method) |
| `gold_ppe` | `gold_ppe.parquet` | PPE roll-forward schedule |
| `gold_elimination` | `gold_elimination.parquet` | Consolidation elimination entries |
| `gold_related_party` | `gold_related_party.parquet` | Related party transactions |

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

Push updated data to the cloud database for Vercel/Render deployment.

**Prerequisites:**
```bash
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
curl https://finance-data-lake.onrender.com/api/v1/health
```

> **Note:** Render deployment (finance-data-lake.onrender.com) ใช้สำหรับ simulation calc เท่านั้น
> ยังไม่มี GL/Sales data บน cloud — Finance KPI pages ใช้ local DuckDB หรือ mock fallback

---

## Full Monthly Refresh (All Steps)

```bash
# 1. Drop new SAP files into 01_Bronze_Raw/ (manual)

# 2-4. Silver + Gold GL Summary + DuckDB in one command:
python orchestrator.py --all
# (run_pipeline.py --all also works — forwards to orchestrator automatically)

# 2-4b. (ถ้าต้องการ audit Gold Parquets ด้วย):
python orchestrator.py --all --include-gold

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
| API returns `{"status": "degraded"}` | DuckDB missing or views stale | `python orchestrator.py --init-db` |
| Silver row count lower than expected | New month file not in Bronze | Verify `01_Bronze_Raw/Sales_Reports/YYYY/` has new file |
| `migrate_to_neon.py` fails auth error | `DATABASE_URL` not set | Check `.env` file |
| `/api/v1/cost-closing/zreport` returns 404 | `sap_cost_closing_app/data/processed/` missing | Run cost closing pipeline in that project |
| `finance_lake.duckdb` not found | DuckDB never initialized | `python orchestrator.py --init-db` |
| API returns old data after ETL | Old DuckDB process using cached views | Restart `uvicorn` |
| `v_ar` ถูก skip ใน init_duckdb | `master_ar_1000.parquet` ยังไม่ได้รัน | `python orchestrator.py --layer silver --domain ar` |
| `create_cashflow.py` error — leadsheet not found | Gold leadsheet ยังไม่มี | รัน `create_leadsheet.py` ก่อน |

---

## Adding a New Fiscal Year

When starting data for a new year (e.g., 2026):

1. **Create Bronze folders:**
   ```bash
   mkdir "01_Bronze_Raw/Sales_Reports/2026"
   mkdir "01_Bronze_Raw/Production/2026"
   ```

2. **Add DuckDB year-specific views** — edit `04_Data_Pipelines/init_duckdb.py`:
   ```python
   YEAR_VIEWS = {
       ...
       "v_sales_2026":      os.path.join(SILVER, "master_sales_2026.parquet"),
       "v_production_2026": os.path.join(SILVER, "master_production_2026.parquet"),
   }
   ```

3. **Add TB period** — edit `backend/routers/financial_tb.py`:
   ```python
   TB_FILES = {
       "2026-03-31": NRV_DIR / "AMC_TB_03.2026_vN.XLSX",
       "2025-12-31": ...,
       ...
   }
   ```

4. **Update `08_Config/data_paths.yaml`** — ไม่ต้องแก้ (ใช้ `{year}` pattern แล้ว)

5. Re-run:
   ```bash
   python orchestrator.py --layer silver --domain sales --year 2026
   python orchestrator.py --layer silver --domain production --year 2026
   python orchestrator.py --init-db
   ```

---

## Initial Cloud Setup (First Time Only)

```bash
# 1. Create free Neon DB at https://neon.tech
#    Copy connection string to .env as DATABASE_URL

# 2. Create schema (run once)
psql "$DATABASE_URL" -f scripts/setup_neon_schema.sql

# 3. Load initial data
python scripts/migrate_to_neon.py

# 4. Set DATABASE_URL in Render/Vercel dashboard
#    Settings → Environment Variables → DATABASE_URL
```
