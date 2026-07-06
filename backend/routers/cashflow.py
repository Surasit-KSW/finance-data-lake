"""
routers/cashflow.py
===================
Cashflow Plan endpoint — /api/v1/cashflow/...

GET /api/v1/cashflow/plan?from=YYYY-MM-DD&to=YYYY-MM-DD
  Returns itemised cash flow plan for the given date range.

Data sources (T1 — local DuckDB only, never Neon/Render):
  v_ar  — AR open items (Net Due Date, Clearing Date available)
  v_ap  — AP open items (Posting Date only — no Net Due Date / Clearing Date)
  02_Silver_Cleaned/treasury_positions_2026.parquet   — TR/PN maturities
  02_Silver_Cleaned/cashflow_plan_2026.parquet        — manual entries

AP limitation: v_ap has no Net Due Date / Clearing Date columns.
  AP items always use Posting Date as due proxy and status='plan'.
"""
from pathlib import Path
from datetime import date, datetime
import uuid
import pandas as pd
from fastapi import APIRouter, Query
from backend.services.db_service import query_df

router    = APIRouter(prefix="/api/v1/cashflow", tags=["Cashflow"])
LAKE_ROOT = Path(__file__).resolve().parents[2]
SILVER    = LAKE_ROOT / "02_Silver_Cleaned"


def _load_parquet_safe(name: str) -> pd.DataFrame:
    """Load parquet, return empty DataFrame if file absent."""
    p = SILVER / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def _safe_float(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def _to_date_str(val) -> str | None:
    """Convert various date representations to YYYY-MM-DD string or None."""
    if val is None or (isinstance(val, float) and val != val):
        return None
    try:
        if isinstance(val, (datetime, date)):
            return val.strftime("%Y-%m-%d")
        return pd.Timestamp(val).strftime("%Y-%m-%d")
    except Exception:
        return None


def _item_status(due_str: str | None, clearing_str: str | None, today: date) -> str:
    """Derive plan/actual/overdue status from due date and clearing date."""
    if clearing_str:
        try:
            if date.fromisoformat(clearing_str) <= today:
                return "actual"
        except ValueError:
            pass
    if due_str:
        try:
            if date.fromisoformat(due_str) < today:
                return "overdue"
        except ValueError:
            pass
    return "plan"


@router.get("/plan")
def get_cashflow_plan(
    from_date: str = Query(..., alias="from", description="Start date YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="End date YYYY-MM-DD"),
):
    today = date.today()
    items: list[dict] = []

    # ── AR items ─────────────────────────────────────────────────────────────
    try:
        ar = query_df(
            """
            SELECT
                "Customer"                    AS customer,
                "Customer Account: Name 1"    AS customer_name,
                "Net Due Date"                AS due_date,
                "Company Code Currency Value" AS amount,
                "Document Number"             AS doc_no,
                "Clearing Date"               AS clearing_date,
                company_code
            FROM v_ar
            WHERE company_code = ?
              AND TRY_CAST("Net Due Date" AS DATE) BETWEEN ? AND ?
              AND TRY_CAST("Company Code Currency Value" AS DOUBLE) > 0
            """,
            ["1000", from_date, to_date],
        )
        cols = set(ar.columns)
        for _, r in ar.iterrows():
            # Support both SQL-aliased names and original column names
            due    = _to_date_str(r.get("due_date") if "due_date" in cols else r.get("Net Due Date"))
            clr    = _to_date_str(r.get("clearing_date") if "clearing_date" in cols else r.get("Clearing Date"))
            status = _item_status(due, clr, today)
            doc_no = (r.get("doc_no") if "doc_no" in cols else r.get("Document Number")) or uuid.uuid4().hex[:8]
            amount = r.get("amount") if "amount" in cols else r.get("Company Code Currency Value")
            cparty = (r.get("customer_name") if "customer_name" in cols else None) or (r.get("Customer Account: Name 1") if "Customer Account: Name 1" in cols else None) or r.get("customer") or r.get("Customer") or ""
            items.append({
                "id":           f"ar-{doc_no}",
                "date":         due or from_date,
                "type":         "ar",
                "source":       "auto",
                "counterparty": str(cparty),
                "amount_thb":   round(_safe_float(amount), 2),
                "status":       status,
                "reference":    str(doc_no),
                "clearing_date": clr,
            })
    except Exception as e:
        print(f"  WARN  AR query failed: {e}")

    # ── AP items ─────────────────────────────────────────────────────────────
    # v_ap has no Net Due Date or Clearing Date — use Posting Date as proxy.
    # All AP items → status='plan'.
    try:
        ap = query_df(
            """
            SELECT
                "Vendor"                  AS vendor,
                "Vendor Account: Name 1"  AS vendor_name,
                "Posting Date"            AS posting_date,
                "Net_Amount"              AS amount,
                "Document Number"         AS doc_no,
                company_code
            FROM v_ap
            WHERE company_code = ?
              AND TRY_CAST("Posting Date" AS DATE) BETWEEN ? AND ?
            """,
            ["1000", from_date, to_date],
        )
        ap_cols = set(ap.columns)
        for _, r in ap.iterrows():
            # Support both SQL-aliased names and original column names
            due    = _to_date_str(r.get("posting_date") if "posting_date" in ap_cols else r.get("Posting Date"))
            raw_amt = r.get("amount") if "amount" in ap_cols else r.get("Net_Amount")
            amt    = _safe_float(raw_amt)
            # AP amounts in v_ap may be positive or negative depending on SAP export;
            # ensure payments are stored as negative
            amount_thb = -abs(amt) if amt != 0 else 0.0
            doc_no = (r.get("doc_no") if "doc_no" in ap_cols else r.get("Document Number")) or uuid.uuid4().hex[:8]
            cparty = (r.get("vendor_name") if "vendor_name" in ap_cols else None) or (r.get("Vendor Account: Name 1") if "Vendor Account: Name 1" in ap_cols else None) or r.get("vendor") or r.get("Vendor") or ""
            items.append({
                "id":           f"ap-{doc_no}",
                "date":         due or from_date,
                "type":         "ap",
                "source":       "auto",
                "counterparty": str(cparty),
                "amount_thb":   round(amount_thb, 2),
                "status":       "plan",
                "reference":    str(doc_no),
                "clearing_date": None,
            })
    except Exception as e:
        print(f"  WARN  AP query failed: {e}")

    # ── Treasury maturity events ──────────────────────────────────────────────
    try:
        pos = _load_parquet_safe("treasury_positions_2026.parquet")
        if not pos.empty and "maturity_date" in pos.columns:
            for col in ("maturity_date",):
                pos[col] = pos[col].astype(str).replace({"NaT": "", "None": "", "nan": ""})
            mask = (
                pos["maturity_date"].apply(lambda d: bool(d and from_date <= d <= to_date))
                & pos["product"].isin(["TR", "PN"])
            )
            for _, r in pos[mask].iterrows():
                amt = _safe_float(r.get("amount_thb", 0))
                items.append({
                    "id":           f"treasury-{r.get('product','')}-{r.get('bank','')}",
                    "date":         str(r["maturity_date"]),
                    "type":         "treasury",
                    "source":       "auto",
                    "counterparty": f"{r.get('bank','')} ({r.get('product','')})",
                    "amount_thb":   round(-abs(amt), 2),   # maturity = repayment outflow
                    "status":       "plan",
                    "reference":    str(r.get("lc_no") or ""),
                    "clearing_date": None,
                })
    except Exception as e:
        print(f"  WARN  treasury query failed: {e}")

    # ── Manual entries ────────────────────────────────────────────────────────
    try:
        year = date.fromisoformat(from_date).year
        manual = _load_parquet_safe(f"cashflow_plan_{year}.parquet")
        if not manual.empty:
            mask = manual["date"].apply(lambda d: bool(d and from_date <= d <= to_date))
            for _, r in manual[mask].iterrows():
                t = str(r.get("type", ""))
                item_type = "manual_in" if t == "receipt" else "manual_out"
                items.append({
                    "id":           f"manual-{uuid.uuid4().hex[:8]}",
                    "date":         str(r["date"]),
                    "type":         item_type,
                    "source":       "manual",
                    "counterparty": str(r.get("note") or ""),
                    "amount_thb":   round(_safe_float(r.get("amount_thb")), 2),
                    "status":       "plan",
                    "reference":    "",
                    "clearing_date": None,
                })
    except Exception as e:
        print(f"  WARN  manual plan query failed: {e}")

    # ── Opening balance from treasury summary ─────────────────────────────────
    opening = 0.0
    try:
        banks = _load_parquet_safe("treasury_banks_2026.parquet")
        if not banks.empty and "balance" in banks.columns:
            opening = round(float(banks["balance"].sum()), 2)
    except Exception:
        pass

    # Sort items by date
    items.sort(key=lambda x: x["date"])

    return {
        "asOf":            today.isoformat(),
        "opening_balance": opening,
        "items":           items,
        "usingMock":       False,
    }
