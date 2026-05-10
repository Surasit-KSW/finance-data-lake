---
description: Open the Streamlit audit analytics dashboard (port 8501)
---

Launch the local Streamlit dashboard for audit analytics.

**Prerequisite — the Finance Data Lake API must be running.** If not, start it first in a separate terminal:
```bash
uvicorn backend.main:app --reload --port 8000
```

**Then launch the dashboard:**
```bash
python run_pipeline.py --dashboard
```

The dashboard will open automatically at: http://localhost:8501

If it doesn't open automatically:
```bash
streamlit run 05_Dashboards/app_01_audit_analytics.py --server.port 8501
```

**What's in the dashboard:**
- GL transaction analysis by account and period
- Sales analytics by product group
- Production cost analysis
- AR aging overview (if `master_ar.parquet` is available)

If the dashboard shows no data, check that:
1. The API is running (`curl http://localhost:8000/api/v1/health`)
2. DuckDB views are initialized (`python run_pipeline.py --init-db`)
3. Silver Parquet files exist in `02_Silver_Cleaned/`
