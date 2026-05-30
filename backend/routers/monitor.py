"""
routers/monitor.py
==================
Production Cost Monitor endpoints — /api/v1/monitor/...

Consumers: fintech-command-center (Monitor module)

Data sources:
  - v_gl         : GL line items (cost accounts 5xxx filtered by cost center)
  - v_gl_summary : Monthly GL aggregates (faster for overview)
  - v_production : Production qty + total cost per plant/order

Endpoints:
  GET /api/v1/monitor/cost-ledger  — GL cost breakdown per plant/quarter
  GET /api/v1/monitor/overview     — Multi-plant summary (rm, conv, volume, gp)

SAP sign convention (v_gl):
  Cost accounts (5xxx debit)    → Net_Amount POSITIVE
  By-product credits (531-532x) → Net_Amount NEGATIVE
  Revenue (4xxx credit)         → Net_Amount NEGATIVE
"""
from fastapi import APIRouter, Query, HTTPException
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1/monitor", tags=["Monitor v1"])

# ─── Constants ──────────────────────────────────────────────────────────────

# GL account prefix → (section, display label)
# Order matters: more specific prefixes first
ACCOUNT_SECTION: list[tuple[str, str, str]] = [
    ("541", "rm",   "Raw Material"),
    ("531", "rm",   "By-product Credit"),   # credit → isCredit=True
    ("532", "rm",   "By-product Credit"),   # credit → isCredit=True
    ("551", "conv", "Direct Labor"),
    ("552", "conv", "Indirect Labor"),
    ("561", "conv", "Electricity"),
    ("562", "conv", "Water / Utilities"),
    ("571", "conv", "Depreciation"),
    ("572", "conv", "Amortisation"),
    ("581", "conv", "Maintenance & Repair"),
    ("591", "conv", "LNG / Natural Gas"),
    ("592", "conv", "Steam / Boiler"),
    ("593", "conv", "Other Fuel"),
    ("599", "conv", "Other Conv. Cost"),
]

CREDIT_PREFIXES = {"531", "532"}

# Cost center prefix per plant (best-effort — calibrate per actual SAP config)
PLANT_CC_PREFIX: dict[str, str] = {
    "1300": "1300",
    "1100": "1100",
    "1200": "1200",
}

PLANT_LABELS: dict[str, str] = {
    "1300": "GI — Plant 1300",
    "1100": "Pipe A1 — Plant 1100",
    "1200": "Pipe A2 — Plant 1200",
}

ALL_PLANTS = ["1300", "1100", "1200"]


# ─── Helpers ────────────────────────────────────────────────────────────────

def _quarter_months(quarter: int) -> list[int]:
    q = max(1, min(4, quarter))
    start = (q - 1) * 3 + 1
    return list(range(start, start + 3))


def _section_for_account(account: str) -> tuple[str, str, bool]:
    """Return (section, label, is_credit) for a GL account code."""
    prefix3 = str(account)[:3]
    is_credit = prefix3 in CREDIT_PREFIXES
    for prefix, section, label in ACCOUNT_SECTION:
        if str(account).startswith(prefix):
            return section, label, is_credit
    if str(account).startswith("5"):
        return "conv", "Other Cost", False
    return "conv", "Other", False


def _in_clause(items: list) -> str:
    """Build SQL IN clause placeholders."""
    return "({})".format(",".join("?" * len(items)))


def _query_gl_by_account(
    year: int,
    months: list[int],
    cc_prefix: str | None,
) -> list[dict]:
    """
    Aggregate v_gl by GL account for cost accounts (5xxx) in the given period.
    Returns list of {account_code, account_name, gl_amount}.
    """
    conds = [
        "CAST(Year AS INTEGER) = ?",
        f"CAST(Month AS INTEGER) IN {_in_clause(months)}",
        '"G/L Account" LIKE \'5%\'',
    ]
    params: list = [year] + months

    if cc_prefix:
        conds.append('"Cost Center: Short Text" LIKE ?')
        params.append(f"{cc_prefix}%")

    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT
                "G/L Account"            AS account_code,
                "G/L Account: Long Text" AS account_name,
                SUM("Net_Amount")        AS gl_amount
            FROM v_gl
            WHERE {where}
            GROUP BY "G/L Account", "G/L Account: Long Text"
            ORDER BY "G/L Account"
            """,
            params,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"GL query failed: {e}")

    return df.to_dict(orient="records")


def _query_production_volume(
    year: int,
    months: list[int],
    plant: str | None = None,
) -> dict[str, float]:
    """
    Return {plant: total_qty} from v_production.
    If plant is specified, returns single-plant dict.
    """
    conds = [
        "CAST(\"Year\" AS INTEGER) = ?",
        f"CAST(\"Month\" AS INTEGER) IN {_in_clause(months)}",
    ]
    params: list = [year] + months

    if plant:
        conds.append('"Plant" = ?')
        params.append(plant)

    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT "Plant", SUM("Production Qty") AS total_qty
            FROM v_production
            WHERE {where}
            GROUP BY "Plant"
            """,
            params,
        )
    except Exception:
        return {}

    if df.empty:
        return {}
    return df.set_index("Plant")["total_qty"].to_dict()


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/cost-ledger")
def get_cost_ledger(
    plant:   str = Query(..., description="Plant code: 1300, 1100, 1200"),
    year:    int = Query(2026),
    quarter: int = Query(1, ge=1, le=4),
):
    """
    GL cost breakdown per plant/quarter → CostLedgerRow[] for Monitor > Cost Ledger page.

    Aggregates v_gl cost accounts (5xxx) filtered by cost center prefix.
    Falls back to all-plant GL if cost center filter returns no data.
    """
    months = _quarter_months(quarter)
    cc_prefix = PLANT_CC_PREFIX.get(plant)

    # Try with cost-center filter first; fall back to no filter
    records = _query_gl_by_account(year, months, cc_prefix)
    cc_filtered = bool(cc_prefix and records)
    if not records and cc_prefix:
        records = _query_gl_by_account(year, months, cc_prefix=None)
        cc_filtered = False

    # Production volume
    vol_map = _query_production_volume(year, months, plant)
    volume = float(sum(vol_map.values()))

    # Build CostLedgerRow[]
    rows: list[dict] = []
    for i, r in enumerate(records, 1):
        acct      = str(r.get("account_code") or "")
        acct_name = str(r.get("account_name") or "")
        gl_amt    = float(r.get("gl_amount") or 0)

        section, default_label, is_credit = _section_for_account(acct)
        # SAP sign: credits stored negative → flip isCredit if negative amount
        if gl_amt < 0:
            is_credit = True
        display_amt = abs(gl_amt)

        rows.append({
            "id":           acct,
            "label":        acct_name or default_label,
            "section":      section,
            "isCredit":     is_credit,
            "qty":          None,
            "qtyUnit":      None,
            "unitPrice":    None,
            "amount":       display_amt,
            "source":       "KSB1",
            "sourceDetail": None,
            "glAccount":    acct,
            "dailyQty":     None,
            "dailyFlag":    None,
            "mb51Qty":      None,
            "mb51DiffPct":  None,
            "mb51Flag":     "MANUAL",
            "glAmount":     display_amt,
            "tbAmount":     None,
            "tbFlag":       "OK",
        })

    return {
        "status":      "ok",
        "plant":       plant,
        "plantLabel":  PLANT_LABELS.get(plant, plant),
        "year":        year,
        "quarter":     quarter,
        "ccFiltered":  cc_filtered,
        "count":       len(rows),
        "data":        rows,
        "meta": {
            "volume": volume,
            "unit":   "T",
        },
    }


@router.get("/overview")
def get_overview(
    year:    int = Query(2026),
    quarter: int = Query(1, ge=1, le=4),
):
    """
    Multi-plant cost summary for Monitor > Cost Overview page.
    Returns PlantCostCard data: rm_cost, conv_cost, volume, gp_margin per plant.
    """
    months = _quarter_months(quarter)

    # Production volume + standard cost per plant
    vol_map = _query_production_volume(year, months)

    # GL cost per plant via cost center filter
    plant_summaries: list[dict] = []

    for plant_code in ALL_PLANTS:
        cc_prefix = PLANT_CC_PREFIX.get(plant_code)
        records   = _query_gl_by_account(year, months, cc_prefix)
        if not records:
            records = _query_gl_by_account(year, months, cc_prefix=None)

        rm_total   = 0.0
        conv_total = 0.0
        for r in records:
            acct    = str(r.get("account_code") or "")
            gl_amt  = float(r.get("gl_amount") or 0)
            section, _, is_credit = _section_for_account(acct)
            net_amt = -abs(gl_amt) if (is_credit or gl_amt < 0) else abs(gl_amt)
            if section == "rm":
                rm_total   += net_amt
            else:
                conv_total += net_amt

        volume    = float(vol_map.get(plant_code, 0))
        total_cost = rm_total + conv_total

        plant_summaries.append({
            "plantName": f"Plant {plant_code}",
            "plant":     plant_code,
            "product":   PLANT_LABELS.get(plant_code, plant_code),
            "rmCost":    round(rm_total, 2),
            "convCost":  round(conv_total, 2),
            "total":     round(total_cost, 2),
            "volume":    round(volume, 3),
            "gpMargin":  None,    # requires revenue data — extend later
            "hasGL":     bool(records),
            "hasTB":     None,    # TB reconcile not yet wired
            "sapScore":  None,
        })

    return {
        "status":  "ok",
        "year":    year,
        "quarter": quarter,
        "plants":  plant_summaries,
        "alerts":  [],   # alert feed from SAP_PENDING/DIFF — extend later
    }
