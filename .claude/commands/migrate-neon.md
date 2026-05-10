---
description: Sync local Parquet data to Neon PostgreSQL for Vercel cloud deployment
---

Push the current Silver and Gold layer data to Neon PostgreSQL. Run this monthly after each SAP data refresh.

**Step 1 — Verify DATABASE_URL is set:**
```bash
python -c "
from dotenv import load_dotenv
import os
load_dotenv()
url = os.environ.get('DATABASE_URL', '')
if url:
    print('OK — DATABASE_URL:', url[:40] + '...')
else:
    print('ERROR: DATABASE_URL not set in .env')
    print('Add: DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require')
"
```

**Step 2 — Verify Silver Parquet files exist (pipeline must have run first):**
```bash
python -c "
import glob
files = glob.glob('02_Silver_Cleaned/*.parquet') + glob.glob('03_Gold_DataMarts/*.parquet')
print(f'{len(files)} Parquet files found:')
for f in files: print(f'  {f}')
"
```

**Step 3 — Run migration** (safe to run multiple times — truncates and reloads all tables):
```bash
python scripts/migrate_to_neon.py
```

**Step 4 — Verify cloud API:**
```bash
curl -s https://your-app.vercel.app/api/v1/health | python -m json.tool
```

The response should show `"backend": "postgresql"` in the `database` field.

**First-time setup only** — create schema before first migration:
```bash
# Run once:
psql "$DATABASE_URL" -f scripts/setup_neon_schema.sql
```

**Note:** After migration, the Vercel deployment automatically uses Neon because `DATABASE_URL` is set in Vercel environment variables. The local API continues to use DuckDB (no `DATABASE_URL` in local `.env` by default).
