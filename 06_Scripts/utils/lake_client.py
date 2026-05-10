"""
lake_client.py
==============
Finance Data Lake — Shared HTTP Client

Import this in any Python project that needs to fetch data from the
Finance Data Lake API instead of reading files directly.

Usage:
    from lake_client import LakeClient

    lake = LakeClient()           # auto-detects URL from env or default
    df_tb  = lake.get_trial_balance("2026-03-31")
    df_gl  = lake.get_gl_transactions(year=2025, account="4111010")
    df_ar  = lake.get_ar_aging()
    status = lake.health()

    # Check if API is running
    if lake.is_available():
        df = lake.get_sales_summary(year=2025)
    else:
        print("Data Lake API not available — use local files")

Install requirements:
    pip install requests pandas

For projects outside the Data Lake directory, set env var:
    DATA_LAKE_URL=http://localhost:8000
"""

import os
import json
from typing import Any
import pandas as pd

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    print("[lake_client] WARNING: 'requests' not installed. Run: pip install requests")

DEFAULT_URL     = "http://localhost:8000"
DEFAULT_TIMEOUT = 30    # seconds
API_PREFIX      = "/api/v1"


class LakeAPIError(Exception):
    """Raised when the Data Lake API returns an error."""
    pass


class LakeClient:
    """
    HTTP client for the Finance Data Lake REST API.

    Parameters
    ----------
    base_url : str, optional
        Base URL of the API. Defaults to DATA_LAKE_URL env var or http://localhost:8000
    timeout : int, optional
        Request timeout in seconds (default 30)
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.base_url = (
            base_url
            or os.environ.get("DATA_LAKE_URL")
            or DEFAULT_URL
        ).rstrip("/")
        self.timeout = timeout
        self._prefix = API_PREFIX

    def _url(self, path: str) -> str:
        return f"{self.base_url}{self._prefix}{path}"

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not _HAS_REQUESTS:
            raise ImportError("Install 'requests': pip install requests")
        url = self._url(path)
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise LakeAPIError(
                f"Cannot connect to Data Lake API at {self.base_url}. "
                "Is the server running? Run: uvicorn backend.main:app --reload"
            )
        except requests.exceptions.Timeout:
            raise LakeAPIError(f"Request timed out after {self.timeout}s: {url}")
        except requests.exceptions.HTTPError as e:
            raise LakeAPIError(f"API error {e.response.status_code}: {e.response.text}")

    def _to_df(self, response: dict) -> pd.DataFrame:
        """Convert API response['data'] to DataFrame."""
        data = response.get("data", [])
        if not data:
            return pd.DataFrame()
        return pd.DataFrame(data)

    # ── Health ──────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """Check if the Data Lake API is running and healthy."""
        try:
            return self._get("/health")
        except LakeAPIError:
            return {"status": "unavailable"}

    def is_available(self) -> bool:
        """Return True if the API is reachable."""
        return self.health().get("status") == "ok"

    # ── Financial / Trial Balance ───────────────────────────────────────────

    def get_trial_balance(self, period: str) -> pd.DataFrame:
        """
        Get Trial Balance for a specific period.

        Parameters
        ----------
        period : str
            Period in YYYY-MM-DD format (e.g. "2026-03-31", "2025-12-31")

        Returns
        -------
        pd.DataFrame with columns: account_code, account_name, balance, fs_item
        """
        resp = self._get(f"/financial/tb/{period}")
        return self._to_df(resp)

    def get_master_tb(self) -> pd.DataFrame:
        """
        Get Master TB account mapping.

        Returns
        -------
        pd.DataFrame with: account_code, account_name, index, caption,
                           balance_dec25, balance_mar26
        """
        resp = self._get("/financial/master-tb")
        return self._to_df(resp)

    def list_tb_periods(self) -> list[dict]:
        """List available Trial Balance periods."""
        resp = self._get("/financial/tb")
        return resp.get("periods", [])

    # ── GL ──────────────────────────────────────────────────────────────────

    def get_gl_transactions(
        self,
        year: int,
        month: int | None = None,
        account: str | None = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Get GL line-item transactions.

        Parameters
        ----------
        year    : int — fiscal year (e.g. 2025)
        month   : int | None — month 1-12 (optional)
        account : str | None — GL account code (e.g. "4111010")
        limit   : int — max rows (default 500, max 5000)
        """
        params = {"year": year, "limit": limit}
        if month:
            params["month"] = month
        if account:
            params["account"] = account
        resp = self._get("/gl/transactions", params=params)
        return self._to_df(resp)

    def get_gl_balance(
        self,
        account: str,
        year: int | None = None,
    ) -> pd.DataFrame:
        """
        Get monthly cumulative balance for a GL account.
        Useful for reconciliation with TB.
        """
        params = {}
        if year:
            params["year"] = year
        resp = self._get(f"/gl/balance/{account}", params=params)
        df = self._to_df(resp)
        return df

    def get_gl_accounts(
        self,
        year: int = 2025,
        search: str | None = None,
    ) -> pd.DataFrame:
        """List all GL accounts with balances for a given year."""
        params: dict = {"year": year}
        if search:
            params["search"] = search
        resp = self._get("/gl/accounts", params=params)
        return self._to_df(resp)

    # ── Audit ───────────────────────────────────────────────────────────────

    def get_ar_aging(
        self,
        as_of_year: int = 2025,
        as_of_month: int = 12,
        customer: str | None = None,
    ) -> pd.DataFrame:
        """Get AR aging report."""
        params: dict = {"as_of_year": as_of_year, "as_of_month": as_of_month}
        if customer:
            params["customer"] = customer
        resp = self._get("/audit/ar-aging", params=params)
        return self._to_df(resp)

    def get_gl_reconcile(self, account: str, year: int = 2025) -> pd.DataFrame:
        """GL reconciliation — monthly balance for account (for reconcile vs TB)."""
        resp = self._get("/audit/gl-reconcile", params={"account": account, "year": year})
        return self._to_df(resp)

    # ── Sales ───────────────────────────────────────────────────────────────

    def get_sales_summary(self, year: int) -> pd.DataFrame:
        """Monthly sales summary by product group."""
        resp = self._get(f"/sales/summary/{year}")
        return self._to_df(resp)

    # ── Cost Closing ────────────────────────────────────────────────────────

    def get_zreport(self, period: str | None = None) -> pd.DataFrame:
        """Z-Report data (cost center actual vs plan)."""
        params = {}
        if period:
            params["period"] = period
        resp = self._get("/cost-closing/zreport", params=params)
        return self._to_df(resp)

    def get_fi_co_diff(
        self,
        period: str | None = None,
        threshold: float = 0.01,
    ) -> pd.DataFrame:
        """FI-CO mismatch report."""
        params: dict = {"threshold": threshold}
        if period:
            params["period"] = period
        resp = self._get("/cost-closing/fi-co-diff", params=params)
        return self._to_df(resp)

    def get_production_cost(
        self,
        year: int = 2026,
        month: int | None = None,
        plant: str | None = None,
    ) -> pd.DataFrame:
        """Production cost summary."""
        params: dict = {"year": year}
        if month:
            params["month"] = month
        if plant:
            params["plant"] = plant
        resp = self._get("/cost-closing/production-cost", params=params)
        return self._to_df(resp)

    def __repr__(self) -> str:
        return f"LakeClient(url={self.base_url}, available={self.is_available()})"


# ── Singleton for convenience ────────────────────────────────────────────────
lake = LakeClient()


# ── CLI test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Finance Data Lake — Client Test")
    print("=" * 50)
    client = LakeClient()
    h = client.health()
    print(f"API Status : {h.get('status')}")
    print(f"URL        : {client.base_url}{client._prefix}")
    print(f"DuckDB     : {h.get('duckdb')}")
    print(f"Views      : {h.get('duckdb_views', [])}")
    print()

    if h.get("status") == "ok":
        print("Available TB periods:")
        for p in client.list_tb_periods():
            status = "OK" if p["available"] else "MISSING"
            print(f"  [{status}] {p['period']} — {p['file']}")
    else:
        print("API not available. Start with:")
        print("  uvicorn backend.main:app --reload --port 8000")
