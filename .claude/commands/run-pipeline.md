---
description: Run the Finance Data Lake ETL pipeline (Silver → Gold → DuckDB refresh)
---

Ask the user which mode they want before running, then execute the appropriate command.

**Option A — Full pipeline (all domains, all years):**
```bash
python run_pipeline.py --all
```

**Option B — Specific domain only:**
```bash
# GL transactions
python run_pipeline.py --layer silver --domain gl

# Sales for a specific year
python run_pipeline.py --layer silver --domain sales --year 2026

# Production for a specific year
python run_pipeline.py --layer silver --domain production --year 2026

# AR (accounts receivable)
python run_pipeline.py --layer silver --domain ar
```

**Option C — Gold aggregation only (after Silver is current):**
```bash
python run_pipeline.py --layer gold
```

**Option D — DuckDB views refresh only (after any Parquet file change):**
```bash
python run_pipeline.py --init-db
```

After the pipeline completes, verify the Parquet output:

```bash
python -c "
import pandas as pd, os, glob
silver = '02_Silver_Cleaned'
for f in sorted(glob.glob(os.path.join(silver, '*.parquet'))):
    df = pd.read_parquet(f)
    print(f'{os.path.basename(f):45s} {len(df):>10,} rows')
"
```

Remind the user: if the API is already running, restart it after the pipeline to pick up new DuckDB data:

```bash
# Stop the running uvicorn (Ctrl+C), then:
uvicorn backend.main:app --reload --port 8000
```

For the full monthly cycle, see `PIPELINE.md` for step-by-step details including Bronze file placement.
