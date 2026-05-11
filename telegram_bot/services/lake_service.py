"""
telegram_bot/services/lake_service.py
======================================
Wraps LakeClient with:
  - In-process TTLCache (5-min TTL)
  - Async-friendly wrappers (sync HTTP calls run in thread pool)
  - Extra endpoints not in LakeClient (P&L, KPI, ETL status)
  - Graceful error handling → user-friendly messages

Never imports backend.* — calls the REST API only.
"""
import sys
import asyncio
import logging
import requests
from typing import Any

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path so lake_client can be found
import os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from telegram_bot.config import settings
from telegram_bot.cache import TTLCache

logger = logging.getLogger(__name__)

_cache = TTLCache(default_ttl=settings.CACHE_TTL_SECONDS)


class LakeServiceError(Exception):
    """Raised when the API call fails."""
    pass


class LakeService:
    """
    Async-friendly wrapper around the Finance Data Lake REST API.
    All public methods are async coroutines — run sync HTTP in executor.
    """

    def __init__(self):
        self._base = settings.DATA_LAKE_URL.rstrip("/")
        self._timeout = 30

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Sync GET. Raises LakeServiceError on any failure."""
        url = f"{self._base}{path}"
        try:
            resp = requests.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise LakeServiceError(
                f"Cannot reach API at {self._base}. "
                "Start: uvicorn backend.main:app --reload --port 8000"
            )
        except requests.exceptions.Timeout:
            raise LakeServiceError(f"Request timed out: {url}")
        except requests.exceptions.HTTPError as e:
            raise LakeServiceError(
                f"API error {e.response.status_code}: {e.response.text[:200]}"
            )

    def _post(self, path: str, json_body: dict | None = None) -> dict:
        """Sync POST."""
        url = f"{self._base}{path}"
        try:
            resp = requests.post(url, json=json_body or {}, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise LakeServiceError(f"Cannot reach API at {self._base}.")
        except requests.exceptions.HTTPError as e:
            raise LakeServiceError(
                f"API error {e.response.status_code}: {e.response.text[:200]}"
            )

    def _to_df(self, resp: dict) -> pd.DataFrame:
        data = resp.get("data", [])
        return pd.DataFrame(data) if data else pd.DataFrame()

    async def _run(self, func, *args, **kwargs) -> Any:
        """Run a sync function in the default thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    # ── Cache helpers ─────────────────────────────────────────────────────────

    def _cget(self, key: str) -> Any | None:
        return _cache.get(key)

    def _cset(self, key: str, value: Any) -> None:
        _cache.set(key, value)

    async def invalidate_all(self) -> int:
        """Clear all cached entries. Returns count removed."""
        return _cache.invalidate()

    def cache_stats(self) -> dict:
        return _cache.stats()

    # ── Health ────────────────────────────────────────────────────────────────

    async def get_health(self) -> dict:
        cached = self._cget("health")
        if cached:
            return cached
        result = await self._run(self._get, "/api/v1/health")
        self._cset("health", result)
        return result

    async def get_lake_status(self) -> dict:
        cached = self._cget("lake_status")
        if cached:
            return cached
        result = await self._run(self._get, "/api/lake/status")
        self._cset("lake_status", result)
        return result

    # ── P&L / Finance ────────────────────────────────────────────────────────

    async def get_pnl(self, year: int) -> dict:
        key = f"pnl:{year}"
        cached = self._cget(key)
        if cached:
            return cached
        resp = await self._run(self._get, f"/api/finance/pnl/{year}")
        data = resp.get("data", {})
        self._cset(key, data)
        return data

    async def get_pnl_compare(self, year1: int, year2: int) -> dict:
        key = f"pnl_compare:{year1}:{year2}"
        cached = self._cget(key)
        if cached:
            return cached
        resp = await self._run(self._get, f"/api/finance/pnl/compare/{year1}/{year2}")
        data = resp.get("data", {})
        self._cset(key, data)
        return data

    async def get_kpi(self, year: int) -> dict:
        key = f"kpi:{year}"
        cached = self._cget(key)
        if cached:
            return cached
        resp = await self._run(self._get, f"/api/finance/kpi/{year}")
        data = resp.get("data", {})
        self._cset(key, data)
        return data

    # ── Sales ─────────────────────────────────────────────────────────────────

    async def get_sales(self, year: int) -> pd.DataFrame:
        key = f"sales:{year}"
        cached = self._cget(key)
        if cached is not None:
            return cached
        resp = await self._run(self._get, f"/api/v1/sales/summary/{year}")
        df = self._to_df(resp)
        self._cset(key, df)
        return df

    # ── AR ────────────────────────────────────────────────────────────────────

    async def get_ar_aging(self, year: int, month: int) -> pd.DataFrame:
        key = f"ar:aging:{year}:{month}"
        cached = self._cget(key)
        if cached is not None:
            return cached
        resp = await self._run(
            self._get, "/api/v1/audit/ar-aging",
            {"as_of_year": year, "as_of_month": month}
        )
        df = self._to_df(resp)
        self._cset(key, df)
        return df

    async def get_ar_summary(self, year: int) -> pd.DataFrame:
        key = f"ar:summary:{year}"
        cached = self._cget(key)
        if cached is not None:
            return cached
        resp = await self._run(
            self._get, "/api/v1/audit/ar-summary", {"year": year}
        )
        df = self._to_df(resp)
        self._cset(key, df)
        return df

    # ── GL ────────────────────────────────────────────────────────────────────

    async def get_gl_accounts(self, year: int) -> pd.DataFrame:
        key = f"gl:accounts:{year}"
        cached = self._cget(key)
        if cached is not None:
            return cached
        resp = await self._run(
            self._get, "/api/v1/gl/accounts", {"year": year}
        )
        df = self._to_df(resp)
        self._cset(key, df)
        return df

    async def get_gl_transactions(
        self, year: int, month: int | None = None, account: str | None = None, limit: int = 100
    ) -> pd.DataFrame:
        # Transactions are not cached (too varied)
        params: dict = {"year": year, "limit": limit}
        if month:
            params["month"] = month
        if account:
            params["account"] = account
        resp = await self._run(self._get, "/api/v1/gl/transactions", params)
        return self._to_df(resp)

    # ── Cost Closing ──────────────────────────────────────────────────────────

    async def get_production_cost(self, year: int, month: int | None = None) -> pd.DataFrame:
        key = f"cost:{year}:{month}"
        cached = self._cget(key)
        if cached is not None:
            return cached
        params: dict = {"year": year}
        if month:
            params["month"] = month
        resp = await self._run(self._get, "/api/v1/cost-closing/production-cost", params)
        df = self._to_df(resp)
        self._cset(key, df)
        return df

    async def get_zreport(self) -> pd.DataFrame:
        cached = self._cget("zreport")
        if cached is not None:
            return cached
        resp = await self._run(self._get, "/api/v1/cost-closing/zreport")
        df = self._to_df(resp)
        self._cset("zreport", df)
        return df

    # ── ETL ───────────────────────────────────────────────────────────────────

    async def trigger_etl(self, domain: str = "all", year: str | None = None) -> dict:
        """POST /api/etl/run — no cache, always fresh."""
        body: dict = {"domain": domain}
        if year:
            body["year"] = year
        resp = await self._run(self._post, "/api/etl/run", body)
        return resp

    async def get_etl_runs(self, limit: int = 5) -> list[dict]:
        resp = await self._run(self._get, "/api/etl/runs", {"limit": limit})
        return resp.get("data", resp.get("runs", []))

    async def get_etl_run(self, run_id: int) -> dict:
        resp = await self._run(self._get, f"/api/etl/runs/{run_id}")
        return resp


# Module-level singleton
lake = LakeService()
