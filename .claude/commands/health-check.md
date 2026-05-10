---
description: Check Finance Data Lake API health, DuckDB views, and Parquet file status
---

Run a comprehensive health check on the Finance Data Lake. Check each layer:

**1. API health (requires API running):**
```bash
curl -s http://localhost:8000/api/v1/health | python -m json.tool
```

Look for `"status": "ok"` and a non-empty `duckdb_views` list.

**2. DuckDB view row counts (requires API running):**
```bash
curl -s http://localhost:8000/api/lake/status | python -m json.tool
```

**3. Parquet files directly (no API needed):**
```bash
python -c "
import pandas as pd, os, glob
silver = '02_Silver_Cleaned'
gold = '03_Gold_DataMarts'
print('=== Silver Layer ===')
for f in sorted(glob.glob(os.path.join(silver, '*.parquet'))):
    df = pd.read_parquet(f)
    print(f'  {os.path.basename(f):45s} {len(df):>10,} rows')
print('=== Gold Layer ===')
for f in sorted(glob.glob(os.path.join(gold, '*.parquet'))):
    df = pd.read_parquet(f)
    print(f'  {os.path.basename(f):45s} {len(df):>10,} rows')
"
```

**4. Test a data endpoint:**
```bash
curl -s "http://localhost:8000/api/v1/gl/transactions?year=2025&limit=3" | python -m json.tool
```

**5. Test Trial Balance:**
```bash
curl -s "http://localhost:8000/api/v1/financial/tb/2026-03-31" | python -m json.tool
```

**Common issues and fixes:**

- API not running → use `/start-api`
- `"status": "degraded"` → run `python run_pipeline.py --init-db`
- DuckDB views missing → run `python run_pipeline.py --all`
- Parquet files empty → Bronze source files missing in `01_Bronze_Raw/`
- Old data after ETL → restart uvicorn to pick up new DuckDB state
