"""
routers/monitor.py
==================
Production Cost Monitor endpoints — /api/v1/monitor/...

Consumers: fintech-command-center (Monitor module)

Data sources:
  - v_gl         : GL line items (cost accounts 5xxx filtered by cost center)
  - v_gl_summary : Monthly GL aggregates (faster for overview)
  - v_production : Production qty + total cost per plant/order (MB52)
  - v_sales      : Sales billing data per plant (VF05)

Endpoints:
  GET /api/v1/monitor/cost-ledger  — GL cost breakdown per plant/quarter
  GET /api/v1/monitor/overview     — Multi-plant summary (rm, conv, volume, gp)
  GET /api/v1/monitor/pnl          — Monthly P&L consolidated (revenue + cost)

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

# GL accounts to exclude from cost analysis (moved from frontend)
# 5391020: ML Variance Adjustment — internal reconciliation entry
# 5211010: Semi-FG COGM — intra-plant transfer, double-counts cost
GL_EXCLUSION: set[str] = {"5391020", "5211010"}

# Cost center prefix per plant — SAP cost centers are 7-digit codes
# Plant 1300 (GI)  → cost centers start with 13 (e.g. 1387120, 1381000)
# Plant 1100 (A1)  → cost centers start with 11 (e.g. 1187201, 1181000)
# Plant 1200 (A2)  → cost centers start with 12 (e.g. 1287300, 1281000)
PLANT_CC_PREFIX: dict[str, str] = {
    "1300": "13",
    "1100": "11",
    "1200": "12",
}

# GL account 3-char prefix → costGroup (for frontend cost-group sub-headers)
ACCOUNT_COST_GROUP: dict[str, str | None] = {
    "541": None,          # rm — raw material (no cost group sub-header)
    "531": None,          # rm — by-product credit
    "532": None,          # rm — by-product credit
    "551": "labor",
    "552": "labor",
    "561": "electricity",
    "562": "electricity",
    "571": "depreciation",
    "572": "depreciation",
    "581": "spare_rm",    # Repair & Maintenance / Spare Parts
    "591": "lng_gas",     # LNG / Natural Gas
    "592": "atm_gas",     # H₂ / N₂ atmosphere gas
    "593": "chemicals",   # Chemicals & supplies
    "599": "other",       # Other conversion cost
}

# Cost center sub-prefix → process key, ordered most-specific first
# Plant 1300 (GI line): CC 1387110–125 = PK, 1387120–125 = CR, 13872xx = GI
# Plant 1100 (A1):  CC 1187xxx = Slit, 11872xx = Forming
# Plant 1200 (A2):  CC 1287xxx = Slit, 12873xx = Forming
CC_PROCESS_BY_PLANT: dict[str, list[tuple[str, str]]] = {
    "1300": [
        ("138711", "pk"),    # Pickling  CC 138711x
        ("138712", "cr"),    # Cold Roll CC 138712x
        ("13872",  "gi"),    # GI Line   CC 13872xx
        ("1381",   "plant"), # Plant-wide overhead
    ],
    "1100": [
        ("11872",  "form"),  # Roll Forming
        ("1187",   "slit"),  # Slitter
        ("1181",   "plant"),
    ],
    "1200": [
        ("12873",  "form"),
        ("1287",   "slit"),
        ("1281",   "plant"),
    ],
}

PLANT_LABELS: dict[str, str] = {
    "1300": "GI — Plant 1300",
    "1100": "Pipe A1 — Plant 1100",
    "1200": "Pipe A2 — Plant 1200",
}

ALL_PLANTS = ["1300", "1100", "1200"]

# Column name for production output qty in v_production (MB52 actual GR qty)
PROD_QTY_COL = "Actual GR QTY"
PROD_AMT_COL = "Actual GR Amount"


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


def _cc_to_process(cc: str | None, plant: str) -> str:
    """Map SAP Cost Center code to frontend process key (pk/cr/gi/slit/form/plant)."""
    if not cc:
        return "plant"
    cc_str = str(cc).strip()
    for prefix, proc in CC_PROCESS_BY_PLANT.get(plant, []):
        if cc_str.startswith(prefix):
            return proc
    return "plant"


def _account_to_cost_group(account: str) -> str | None:
    """Return frontend costGroup key for a GL account, or None for rm/credit accounts."""
    return ACCOUNT_COST_GROUP.get(str(account)[:3])


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
    Applies GL_EXCLUSION filter.
    Returns list of {account_code, account_name, cost_center, gl_amount}.

    Plant isolation strategy (two-tier, same cc_prefix for both):
      • Conv accounts (non-541x): filter by Cost Center LIKE '{cc_prefix}%'
        SAP posts conversion costs to cost centers with plant-specific prefix.
      • RM accounts (541x): Cost Center is NULL in GL (posted directly from MB movement).
        Filter instead by Reference (SAP production order number) LIKE '{cc_prefix}%'
        e.g. Plant 1300 → orders 1381xxxxxx, 1382xxxxxx all start with '13'.
    """
    # GL accounts in v_gl are stored as float (e.g. 5211010.0) — compare as BIGINT to avoid
    # "5211010.0" ≠ "5211010" string mismatch that would silently skip the exclusion filter.
    excl_ints = [int(a) for a in GL_EXCLUSION]
    excl_placeholders = _in_clause(excl_ints) if excl_ints else "(-1)"
    conds = [
        "CAST(Year AS INTEGER) = ?",
        f"CAST(Month AS INTEGER) IN {_in_clause(months)}",
        "CAST(\"G/L Account\" AS VARCHAR) LIKE '5%'",
        f"CAST(CAST(\"G/L Account\" AS DOUBLE) AS BIGINT) NOT IN {excl_placeholders}",
    ]
    params: list = [year] + months + excl_ints

    if cc_prefix:
        # Conv: Cost Center prefix  |  RM (541x): Production order Reference prefix
        conds.append("""
            (
                CAST("Cost Center" AS VARCHAR) LIKE ?
                OR (
                    CAST("G/L Account" AS VARCHAR) LIKE '541%'
                    AND "Cost Center" IS NULL
                    AND CAST(Reference AS VARCHAR) LIKE ?
                )
            )
        """)
        params.append(f"{cc_prefix}%")
        params.append(f"{cc_prefix}%")

    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT
                CAST("G/L Account" AS VARCHAR)              AS account_code,
                CAST("G/L Account: Long Text" AS VARCHAR)   AS account_name,
                COALESCE(CAST("Cost Center" AS VARCHAR), '') AS cost_center,
                SUM(net_amount)                             AS gl_amount
            FROM v_gl
            WHERE {where}
            GROUP BY "G/L Account", "G/L Account: Long Text", "Cost Center"
            ORDER BY "G/L Account", "Cost Center"
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
    Return {plant: total_qty_MT} from v_production (finished goods only).

    Filters to finished-goods material prefixes (20GIC, 20ZMC, 20GCU, 20GIC, etc.)
    to exclude semi-finished products (20CRC Cold Rolled Coil).
    Unit in SAP export is KG → divide by 1000 to return MT.

    Plant in v_production is string (added by ETL from filename prefix).
    """
    # v_production columns are case-sensitive (quoted DDL): "Year", "Month", "Material", "Plant"
    conds = [
        'CAST("Year" AS INTEGER) = ?',
        f'CAST("Month" AS INTEGER) IN {_in_clause(months)}',
        # Exclude semi-finished CRC (20CRC) — keep finished coated products
        '"Material" NOT LIKE \'20CRC%\'',
    ]
    params: list = [year] + months

    if plant:
        conds.append('"Plant" = ?')
        params.append(str(plant))

    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT
                "Plant",
                SUM("{PROD_QTY_COL}") / 1000.0 AS total_qty_mt
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
    return {str(k): float(v) for k, v in df.set_index("Plant")["total_qty_mt"].to_dict().items()}


def _query_revenue_by_plant(
    year: int,
    months: list[int],
    plant: str | None = None,
) -> dict[str, float]:
    """
    Return {plant: net_revenue_thb} from gold_revenue_monthly (pre-aggregated Gold table).
    86 rows total vs 165K raw rows in v_sales — much faster.
    """
    conds = [
        "year = ?",
        f"month IN {_in_clause(months)}",
    ]
    params: list = [year] + months

    if plant:
        conds.append("plant = ?")
        params.append(str(plant))

    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT
                plant                    AS plant_code,
                SUM(revenue_thb)         AS revenue
            FROM gold_revenue_monthly
            WHERE {where}
            GROUP BY plant
            """,
            params,
        )
    except Exception:
        return {}

    if df.empty:
        return {}
    df["plant_code"] = df["plant_code"].astype(str).str.replace(r"\.0$", "", regex=True)
    return df.set_index("plant_code")["revenue"].to_dict()


def _query_gp_by_plant(
    year: int,
    months: list[int],
    plant: str | None = None,
) -> dict[str, dict]:
    """
    Return {plant: {revenue, cogs_std, cogs_ml, cogs_other, cogs_total, gp_actual, gp_margin_pct}}
    from gold_gp_by_plant (pre-computed Gold table with company-pool COGS allocation).
    """
    conds = [
        "\"Year\" = ?",
        f"\"Month\" IN {_in_clause(months)}",
    ]
    params: list = [year] + months

    if plant:
        conds.append("\"Plant\" = ?")
        params.append(str(plant))

    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT
                "Plant"              AS plant_code,
                SUM(revenue_thb)     AS revenue,
                SUM(cogs_std_thb)    AS cogs_std,
                SUM(cogs_ml_thb)     AS cogs_ml,
                SUM(cogs_other_thb)  AS cogs_other,
                SUM(cogs_total_thb)  AS cogs_total,
                SUM(gp_actual)       AS gp_actual
            FROM gold_gp_by_plant
            WHERE {where}
            GROUP BY "Plant"
            """,
            params,
        )
    except Exception:
        return {}

    if df.empty:
        return {}

    df["plant_code"] = df["plant_code"].astype(str).str.replace(r"\.0$", "", regex=True)
    result = {}
    for _, row in df.iterrows():
        rev = float(row["revenue"] or 0)
        gp  = float(row["gp_actual"] or 0)
        result[row["plant_code"]] = {
            "revenue":     round(rev, 2),
            "cogs_std":    round(float(row["cogs_std"]  or 0), 2),
            "cogs_ml":     round(float(row["cogs_ml"]   or 0), 2),
            "cogs_other":  round(float(row["cogs_other"] or 0), 2),
            "cogs_total":  round(float(row["cogs_total"] or 0), 2),
            "gp_actual":   round(gp, 2),
            "gp_margin":   round(gp / rev * 100, 2) if rev > 0 else None,
        }
    return result


def _query_tb_amounts(
    year: int,
    months: list[int],
    cc_prefix: str | None,
) -> dict[str, float] | None:
    """
    Return {account: raw_amount} from v_gl — same CC filter as glAmount
    but WITHOUT GL_EXCLUSION applied.

    Purpose: cross-check that GL exclusion accounts (5391020, 5211010) have
    no impact on this plant/period. If tbAmount == glAmount → "OK".
    If they differ → excluded accounts have postings here → "DIFF".

    Uses v_gl directly (not v_gl_summary) so cost-center filter is preserved.
    Returns None on query error.
    """
    conds = [
        "CAST(Year AS INTEGER) = ?",
        f"CAST(Month AS INTEGER) IN {_in_clause(months)}",
        "CAST(\"G/L Account\" AS VARCHAR) LIKE '5%'",
    ]
    params: list = [year] + months

    if cc_prefix:
        conds.append('CAST("Cost Center" AS VARCHAR) LIKE ?')
        params.append(f"{cc_prefix}%")

    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT
                CAST("G/L Account" AS VARCHAR) AS account_code,
                SUM(net_amount)                AS tb_amount
            FROM v_gl
            WHERE {where}
            GROUP BY "G/L Account"
            """,
            params,
        )
    except Exception:
        return None

    if df.empty:
        return None
    return {str(k): float(v) for k, v in df.set_index("account_code")["tb_amount"].to_dict().items()}


TB_DIFF_TOLERANCE  = 0.01  # 1% tolerance — flags if excluded accounts have impact
MB51_DIFF_TOLERANCE = 0.02  # 2% → OK vs DIFF (total GL RM vs MB51 DM reconciliation)


def _query_mb51_total_dm(year: int, months: list[int], plant: str) -> float | None:
    """
    Sum total Direct Material cost from v_mb51 for a plant/period.

    v_mb51 is aggregated per production order (no GL account column), so this
    function is used for total-level GL RM vs MB51 DM reconciliation only.
    Returns THB total or None if v_mb51 is unavailable or has no data.
    """
    try:
        sql = f"""
            SELECT SUM(gi_dm_amount) AS total_dm
            FROM v_mb51
            WHERE CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) IN {_in_clause(months)}
              AND CAST("Plant" AS VARCHAR) = ?
        """
        df = query_df(sql, [year, *months, str(plant)])
        if df is None or df.empty:
            return None
        val = df.iloc[0]["total_dm"]
        return float(val) if val is not None else None
    except Exception:
        return None


def _query_mb51_rm_breakdown(
    year: int,
    months: list[int],
    plant: str,
) -> list[dict] | None:
    """
    Return RM input cost breakdown from v_mb51 (master_mb51_2026.parquet).
    Groups: HRC, GIC, CRC, Chemical, Other.

    Returns list of {material_type, label, amount_thb, pct_of_total}
    sorted by amount descending. Returns None if v_mb51 not available.
    """
    try:
        df = query_df(
            f"""
            SELECT
                SUM(gi_hrc_amount)    AS hrc,
                SUM(gi_gic_amount)    AS gic,
                SUM(gi_crc_amount)    AS crc,
                SUM(gi_chem_amount)   AS chem,
                SUM(gi_other_amount)  AS other_amt,
                SUM(gi_dm_amount)     AS dm_total,
                SUM(gi_total_amount)  AS grand_total
            FROM v_mb51
            WHERE CAST("Year" AS INTEGER) = ?
              AND CAST("Month" AS INTEGER) IN {_in_clause(months)}
              AND CAST("Plant" AS VARCHAR) = ?
            """,
            [year] + months + [str(plant)],
        )
    except Exception:
        return None

    if df.empty:
        return None

    row = df.iloc[0]
    total = float(row["dm_total"] or 0)
    if total <= 0:
        return None

    LABELS = {
        "HRC":   "Hot Rolled Coil",
        "GIC":   "GIC (Semi-Finished)",
        "CRC":   "Cold Rolled Coil",
        "CHEM":  "Chemicals",
        "OTHER": "Other Direct Materials",
    }

    items = [
        ("HRC",   float(row["hrc"]      or 0)),
        ("GIC",   float(row["gic"]      or 0)),
        ("CRC",   float(row["crc"]      or 0)),
        ("CHEM",  float(row["chem"]     or 0)),
        ("OTHER", float(row["other_amt"]or 0)),
    ]
    items.sort(key=lambda x: x[1], reverse=True)

    return [
        {
            "material_type": code,
            "label":         LABELS.get(code, code),
            "amount_thb":    round(amt, 2),
            "pct_of_total":  round(amt / total * 100, 1) if total > 0 else 0.0,
        }
        for code, amt in items
        if abs(amt) > 0
    ]


def _check_tb_data(plant: str, year: int, months: list[int]) -> bool | None:
    """Return True if any GL cost data exists for this plant/period (used as TB proxy in overview)."""
    cc_prefix = PLANT_CC_PREFIX.get(plant)
    result = _query_tb_amounts(year, months, cc_prefix)
    if result is None:
        return None
    return bool(result)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/cost-ledger")
def get_cost_ledger(
    plant:   str      = Query(..., description="Plant code: 1300, 1100, 1200"),
    year:    int      = Query(2026),
    quarter: int      = Query(1, ge=1, le=4),
    month:   int | None = Query(None, ge=1, le=12, description="Specific month (overrides quarter)"),
):
    """
    GL cost breakdown per plant/quarter (or month) → CostLedgerRow[] for Monitor > Cost Ledger.

    Aggregates v_gl cost accounts (5xxx) filtered by cost center prefix.
    Rows include process (pk/cr/gi/slit/form/plant) and costGroup derived from
    SAP cost center and GL account prefix — ready for CostLedgerTable grouping.
    Excludes internal accounts: 5391020 (ML Variance), 5211010 (Semi-FG COGM).
    Falls back to all-plant GL if cost center filter returns no data.
    """
    from collections import defaultdict

    months    = [month] if month else _quarter_months(quarter)
    cc_prefix = PLANT_CC_PREFIX.get(plant)

    # Try with cost-center filter first; fall back to no filter
    raw_records = _query_gl_by_account(year, months, cc_prefix)
    cc_filtered = bool(cc_prefix and raw_records)
    if not raw_records and cc_prefix:
        raw_records = _query_gl_by_account(year, months, cc_prefix=None)
        cc_filtered = False

    # ── Group raw records by (process, account) ──────────────────────────────
    # Raw records have one row per (account, cost_center).
    # We map each cost_center → process, then sum within (process, account).
    GroupKey = tuple  # (process, account_code)
    grouped_amt: dict[GroupKey, float] = defaultdict(float)
    acct_meta: dict[str, tuple[str, str]] = {}   # account_code → (account_name, section_label)

    for r in raw_records:
        acct = str(r.get("account_code") or "")
        cc   = str(r.get("cost_center") or "")
        amt  = float(r.get("gl_amount") or 0)
        proc = _cc_to_process(cc, plant)
        grouped_amt[(proc, acct)] += amt
        if acct not in acct_meta:
            _, default_label, _ = _section_for_account(acct)
            acct_meta[acct] = (str(r.get("account_name") or ""), default_label)

    # Production volume (MT) — used as unit cost denominator
    vol_map = _query_production_volume(year, months, plant)
    volume  = float(sum(vol_map.values()))

    # TB amounts (account-level, no process split) for cross-check
    tb_map = _query_tb_amounts(year, months, cc_prefix)

    # MB51 total DM for RM reconciliation (total-level only — v_mb51 has no GL account column)
    mb51_total_dm = _query_mb51_total_dm(year, months, plant)

    # ── Build CostLedgerRow[] ─────────────────────────────────────────────────
    # Sort: process order (pk < cr < gi < slit < form < plant), then account
    PROC_ORDER = {"pk": 0, "cr": 1, "gi": 2, "slit": 0, "form": 1, "plant": 99}
    sorted_keys = sorted(
        grouped_amt.keys(),
        key=lambda k: (PROC_ORDER.get(k[0], 99), k[1]),
    )

    rows: list[dict] = []
    for proc, acct in sorted_keys:
        gl_amt    = grouped_amt[(proc, acct)]
        acct_name, default_label = acct_meta.get(acct, ("", ""))

        section, _, is_credit = _section_for_account(acct)
        if gl_amt < 0:
            is_credit = True
        display_amt = abs(gl_amt)

        cost_group = _account_to_cost_group(acct)

        # qty / unitPrice semantics:
        #   RM rows  — per-material consumption qty not available from v_mb51 (no GL account column).
        #              Leave qty/unitPrice null; mb51Flag assigned after loop from total reconciliation.
        #   Conv rows — no material qty; unitPrice = cost per output tonne (THB/T produced).
        if section == "rm":
            qty        = None
            qty_unit   = None
            unit_price = None
            mb51_flag  = None   # assigned after loop
        else:
            qty        = None
            qty_unit   = None
            unit_price = round(display_amt / volume, 2) if volume > 0 else None
            mb51_flag  = "MANUAL"   # conversion cost — MB51 not applicable

        # tbAmount: compare process-grouped amount against account-level TB total
        # (TB doesn't split by process — this is an approximate cross-check)
        tb_raw = tb_map.get(acct) if tb_map is not None else None
        if tb_raw is None:
            tb_amount, tb_flag = None, "NO_TB"
        else:
            tb_amount = round(abs(tb_raw), 2)
            diff_pct  = abs(display_amt - tb_amount) / max(tb_amount, 1)
            tb_flag   = "OK" if diff_pct <= TB_DIFF_TOLERANCE else "DIFF"

        # Unique id: combine process + account so same account in different processes is distinct
        row_id = f"{proc}_{acct}" if proc != "plant" else acct

        rows.append({
            "id":           row_id,
            "label":        acct_name or default_label,
            "section":      section,
            "isCredit":     is_credit,
            "process":      proc,
            "costGroup":    cost_group,
            "qty":          qty,
            "qtyUnit":      qty_unit,
            "unitPrice":    unit_price,
            "amount":       round(display_amt, 2),
            "source":       "KSB1" if section == "conv" else "MB51",
            "sourceDetail": None,
            "glAccount":    acct,
            "dailyQty":     None,
            "dailyFlag":    None,
            "mb51Qty":      None,
            "mb51DiffPct":  None,
            "mb51Flag":     mb51_flag,   # None for RM (assigned after loop), "MANUAL" for conv
            "glAmount":     round(display_amt, 2),
            "tbAmount":     tb_amount,
            "tbFlag":       tb_flag,
        })

    # ── Post-loop: MB51 total reconciliation + assign RM flags ──────────────────
    # Sum GL RM cost (non-credit rows in rm section)
    total_gl_rm = sum(
        abs(r["glAmount"])
        for r in rows
        if r["section"] == "rm" and not r["isCredit"]
    )

    if mb51_total_dm is not None and mb51_total_dm > 0 and total_gl_rm > 0:
        recon_diff  = (total_gl_rm - mb51_total_dm) / mb51_total_dm
        rm_flag     = "OK" if abs(recon_diff) <= MB51_DIFF_TOLERANCE else "DIFF"
        mb51_reconcile = {
            "total_gl_rm":   round(total_gl_rm, 2),
            "total_mb51_dm": round(mb51_total_dm, 2),
            "diff_pct":      round(recon_diff * 100, 2),
            "flag":          rm_flag,
        }
    else:
        rm_flag        = "MANUAL"
        mb51_reconcile = None

    # Assign computed flag to all RM rows (mb51_flag was left None during loop)
    for r in rows:
        if r["mb51Flag"] is None:
            r["mb51Flag"] = rm_flag

    # MB51 RM input cost breakdown (HRC/GIC/CRC/Chemical)
    rm_breakdown = _query_mb51_rm_breakdown(year, months, plant)

    return {
        "status":      "ok",
        "plant":       plant,
        "plantLabel":  PLANT_LABELS.get(plant, plant),
        "year":        year,
        "quarter":     quarter,
        "month":       month,
        "ccFiltered":  cc_filtered,
        "excludedAccounts": sorted(GL_EXCLUSION),
        "count":       len(rows),
        "data":        rows,
        "rmBreakdown":    rm_breakdown,
        "mb51Reconcile":  mb51_reconcile,
        "meta": {
            "volume": round(volume, 3),
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
    Includes simple alert detection for zero-production periods.
    """
    months = _quarter_months(quarter)
    vol_map  = _query_production_volume(year, months)
    gp_map   = _query_gp_by_plant(year, months)

    plant_summaries: list[dict] = []
    alerts: list[dict] = []

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

        volume = float(vol_map.get(plant_code, 0))

        # GP from gold_gp_by_plant (company-pool allocation, validated Q1 2026)
        gp_data  = gp_map.get(plant_code, {})
        revenue  = gp_data.get("revenue", 0.0)
        gp_actual = gp_data.get("gp_actual", None)
        gp_margin = gp_data.get("gp_margin", None)

        # TB check
        has_tb = _check_tb_data(plant_code, year, months)

        # SAP score
        sap_score = None
        if records:
            key_prefixes = ("541", "551", "571")
            found = {
                p for r in records for p in key_prefixes
                if str(r.get("account_code", "")).startswith(p)
            }
            sap_score = {"ok": len(found), "total": len(key_prefixes)}

        plant_summaries.append({
            "plantName":  f"Plant {plant_code}",
            "plant":      plant_code,
            "product":    PLANT_LABELS.get(plant_code, plant_code),
            "rmCost":     round(rm_total, 2),
            "convCost":   round(conv_total, 2),
            "total":      round(rm_total + conv_total, 2),
            "volume":     round(volume, 3),
            "revenue":    round(revenue, 2),
            "gpActual":   round(gp_actual, 2) if gp_actual is not None else None,
            "gpMargin":   gp_margin,
            "cogsStd":    gp_data.get("cogs_std"),
            "cogsMl":     gp_data.get("cogs_ml"),
            "cogsTotal":  gp_data.get("cogs_total"),
            "hasGL":      bool(records),
            "hasTB":      has_tb,
            "sapScore":   sap_score,
        })

        # Alert: has GL cost but no production volume
        total_cost = rm_total + conv_total
        if total_cost > 0 and volume == 0:
            alerts.append({
                "plant":  plant_code,
                "flag":   "SAP_PENDING",
                "detail": f"Plant {plant_code}: มี GL cost ฿{total_cost/1e6:.1f}M แต่ไม่พบ production qty ใน v_production",
            })

        # Alert: GP margin negative
        if gp_margin is not None and gp_margin < 0:
            alerts.append({
                "plant":  plant_code,
                "flag":   "DIFF",
                "detail": f"Plant {plant_code}: GP Margin ติดลบ ({gp_margin:.1f}%) — ตรวจสอบ cost allocation",
            })

    return {
        "status":  "ok",
        "year":    year,
        "quarter": quarter,
        "plants":  plant_summaries,
        "alerts":  alerts,
    }


@router.get("/pnl")
def get_pnl(
    year:    int = Query(2026),
    quarter: int = Query(1, ge=1, le=4),
):
    """
    Monthly P&L breakdown per quarter — Revenue + Cost → GP per month/plant.
    Uses v_sales (Net Value THB) for revenue, v_gl (5xxx) for production cost.
    """
    months = _quarter_months(quarter)
    month_labels = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
                    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
                    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

    # ── Monthly Revenue from v_sales ────────────────────────────────────────
    try:
        rev_df = query_df(
            f"""
            SELECT
                CAST(Month AS INTEGER)   AS month,
                CAST(Plant AS VARCHAR)   AS plant_code,
                SUM("Net Value(THB)")    AS revenue
            FROM v_sales
            WHERE CAST(Year AS INTEGER) = ?
              AND CAST(Month AS INTEGER) IN {_in_clause(months)}
              AND "Net Value(THB)" > 0
              AND (Cancelled = 'nan' OR Cancelled IS NULL)
            GROUP BY Month, Plant
            ORDER BY Month, Plant
            """,
            [year] + months,
        )
    except Exception:
        rev_df = None

    # ── Monthly Cost from v_gl (5xxx, exclude internal accounts) ───────────
    excl_ph = _in_clause(list(GL_EXCLUSION))
    try:
        cost_df = query_df(
            f"""
            SELECT
                CAST(Month AS INTEGER)   AS month,
                SUM(CASE WHEN "G/L Account" LIKE '541%'
                         OR "G/L Account" LIKE '531%'
                         OR "G/L Account" LIKE '532%'
                    THEN net_amount ELSE 0 END) AS rm_cost,
                SUM(CASE WHEN "G/L Account" LIKE '5%'
                         AND "G/L Account" NOT LIKE '541%'
                         AND "G/L Account" NOT LIKE '531%'
                         AND "G/L Account" NOT LIKE '532%'
                    THEN net_amount ELSE 0 END) AS conv_cost
            FROM v_gl
            WHERE CAST(Year AS INTEGER) = ?
              AND CAST(Month AS INTEGER) IN {_in_clause(months)}
              AND "G/L Account" LIKE '5%'
              AND "G/L Account" NOT IN {excl_ph}
            GROUP BY Month
            ORDER BY Month
            """,
            [year] + months + list(GL_EXCLUSION),
        )
    except Exception:
        cost_df = None

    # ── Build monthly P&L rows ───────────────────────────────────────────────
    monthly_pnl = []
    for mo in months:
        label = month_labels.get(mo, str(mo))

        # Revenue: sum across all plants for this month
        revenue = 0.0
        if rev_df is not None and not rev_df.empty:
            mo_rev = rev_df[rev_df["month"] == mo]
            revenue = float(mo_rev["revenue"].sum()) if not mo_rev.empty else 0.0

        # Costs
        rm_cost = conv_cost = 0.0
        if cost_df is not None and not cost_df.empty:
            mo_cost = cost_df[cost_df["month"] == mo]
            if not mo_cost.empty:
                rm_cost   = float(mo_cost.iloc[0]["rm_cost"])
                conv_cost = float(mo_cost.iloc[0]["conv_cost"])

        # Credits are stored negative → negate rm_cost if negative
        if rm_cost < 0:
            rm_cost = abs(rm_cost)

        gp = revenue - rm_cost - conv_cost

        monthly_pnl.append({
            "label":    label,
            "month":    mo,
            "revenue":  round(revenue, 2),
            "rmCost":   round(rm_cost, 2),
            "convCost": round(conv_cost, 2),
            "gp":       round(gp, 2),
        })

    # ── Per-plant product summary (GP from gold_gp_by_plant) ────────────────
    products = []
    gp_by_plant  = _query_gp_by_plant(year, months)
    vol_by_plant = _query_production_volume(year, months)

    for plant_code in ALL_PLANTS:
        gp_data     = gp_by_plant.get(plant_code, {})
        plant_rev   = gp_data.get("revenue", 0.0)
        plant_gp    = gp_data.get("gp_actual")
        plant_margin = gp_data.get("gp_margin")
        plant_vol   = float(vol_by_plant.get(plant_code, 0))
        plant_label = PLANT_LABELS.get(plant_code, plant_code)

        products.append({
            "product":     plant_label,
            "plant":       plant_code,
            "volSold":     round(plant_vol, 1),
            "volProduced": round(plant_vol, 1),
            "revenue":     round(plant_rev, 2),
            "gpActual":    round(plant_gp, 2) if plant_gp is not None else None,
            "margin":      plant_margin,
        })

    has_data = any(row["revenue"] > 0 or row["rmCost"] > 0 for row in monthly_pnl)

    return {
        "status":      "ok",
        "year":        year,
        "quarter":     quarter,
        "usingMock":   not has_data,
        "monthlyPnl":  monthly_pnl,
        "products":    products,
    }
