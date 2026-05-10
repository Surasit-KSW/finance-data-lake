---
description: Scaffold a new versioned API endpoint in the Finance Data Lake (/api/v1/)
---

Collect from the user before writing any code:
1. The domain name (e.g., `inventory`, `payroll`, `ap`)
2. The endpoint path (e.g., `/api/v1/inventory/summary`)
3. What data it serves (which DuckDB view or PostgreSQL table)
4. Which projects will consume it

Then create the router file and register it.

**Pattern — create `backend/routers/<domain>.py`:**

```python
"""
routers/<domain>.py
===================
<Description> — /api/v1/<domain>/...
Consumers: <which external projects will use this>
"""
from fastapi import APIRouter, Query
from backend.services.db_service import query_df   # NOT duck_service

router = APIRouter(prefix="/api/v1/<domain>", tags=["<Domain> v1"])


@router.get("/summary")
def get_summary(
    year: int = Query(..., description="Fiscal year"),
):
    """Summary description here."""
    df = query_df(
        """
        SELECT ...
        FROM <view_or_table>
        WHERE EXTRACT(YEAR FROM "date_column") = ?
        ORDER BY ...
        """,
        [year],
    )
    return {
        "status": "ok",
        "year":   year,
        "count":  len(df),
        "data":   df.to_dict(orient="records"),
    }
```

**SQL rules — must work on both DuckDB and PostgreSQL:**
- Use `EXTRACT(YEAR FROM col)` — NOT `strftime('%Y', col)`
- Use `EXTRACT(MONTH FROM col)` — NOT `strftime('%m', col)`
- Use `?` as parameter placeholder (db_service converts to `%s` for psycopg2)
- Use `ILIKE` for case-insensitive string matching (both DBs support it)
- Import from `db_service`, not `duck_service`

**Register in `backend/main.py`:**
```python
from backend.routers import <domain>
app.include_router(<domain>.router)
```

**Also register in `api/index.py`** (Vercel entry point) if it should be available in the cloud:
```python
from backend.routers import <domain>
app.include_router(<domain>.router)
```

**Test the new endpoint:**
```bash
curl -s "http://localhost:8000/api/v1/<domain>/summary?year=2025" | python -m json.tool
```

**Docs appear automatically** at: http://localhost:8000/docs

**Update `CLAUDE.md`** — add the new endpoint to the API Endpoint Reference table.
