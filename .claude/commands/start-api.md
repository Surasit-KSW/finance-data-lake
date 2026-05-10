---
description: Start the Finance Data Lake FastAPI server on port 8000
---

Start the local Finance Data Lake API server.

Run from the project root (`D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake`):

```bash
uvicorn backend.main:app --reload --port 8000
```

After starting, confirm it's running:

```bash
curl -s http://localhost:8000/api/v1/health
```

Then open the interactive docs at: http://localhost:8000/docs

If port 8000 is already in use, find and kill the process:

```bash
netstat -ano | findstr :8000
# Then: taskkill /PID <pid> /F
```

If the API starts but shows `{"status": "degraded"}`, the DuckDB views need to be refreshed:

```bash
python run_pipeline.py --init-db
```
