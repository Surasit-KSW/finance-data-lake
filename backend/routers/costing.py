"""
routers/costing.py
==================
AMC Costing Conclusion endpoint — /api/v1/costing/...

Provides consolidated monthly P&L for AMC (GI+A1+A2) Jan-May 2026,
mirroring the Conclusion sheet structure in Costing_AMC_2026.xlsx.

Key logic:
  - Revenue: gold_gp_by_plant (pre-aggregated Gold table)
  - Scrap income: v_gl GL 4211xxx
  - RM by plant: v_gl GL 5411010 (GI) + 5411010+5411020 (A1/A2) dual-filter by CC prefix
  - Internal RM elimination: v_gl GL 5411020 CC LIKE '11%' OR '12%' (negative)
  - Conv by plant: v_gl GL 55x-59x filtered by CC prefix
  - Transport: v_gl GL 6111030
  - Claims: v_gl GL 4112xxx (negate — stored as negative credits)
  - Interest: v_gl GL 811xxx

GL exclusions: 5391020 (ML variance), 5211010 (Semi-FG COGM)
"""
from fastapi import APIRouter, Query
from backend.services.db_service import query_df

router = APIRouter(prefix="/api/v1/costing", tags=["Costing v1"])

# ── Constants ────────────────────────────────────────────────────────────────

GL_EXCL_INTS = [5391020, 5211010]
PLANT_CC     = {"gi": "13", "a1": "11", "a2": "12"}
MONTHS_ALL   = list(range(1, 13))


def _in_clause(values: list) -> str:
    return "(" + ",".join("?" * len(values)) + ")"


def _to_month_dict(df, val_col: str) -> dict:
    """Convert dataframe with Month column → {month_int: float}."""
    result = {}
    for _, row in df.iterrows():
        m = int(row.get("month") or row.get("Month") or 0)
        if m:
            result[m] = round(float(row.get(val_col) or 0), 2)
    return result


def _zero_months(months: list[int]) -> dict:
    return {m: 0.0 for m in months}


# ── Data Query Helpers ───────────────────────────────────────────────────────

def _revenue_monthly(year: int, months: list[int]) -> dict:
    """Total AMC revenue per month from gold_gp_by_plant."""
    try:
        df = query_df(
            f"""
            SELECT CAST(Month AS INTEGER) AS month,
                   SUM(revenue_thb) AS revenue
            FROM gold_gp_by_plant
            WHERE CAST(Year AS INTEGER) = ?
              AND CAST(Month AS INTEGER) IN {_in_clause(months)}
              AND CAST(CAST(Plant AS DOUBLE) AS BIGINT) IN (1100, 1200, 1300)
            GROUP BY month ORDER BY month
            """,
            [year] + months,
        )
        return _to_month_dict(df, "revenue")
    except Exception:
        return _zero_months(months)


def _gl_monthly(
    year: int,
    months: list[int],
    gl_like: list[str],            # e.g. ['4211%'] or ['5411010']
    cc_like: list[str] | None,     # e.g. ['13%'] or None (all plants)
    use_dual_filter: bool = False,  # True = RM dual-filter (CC OR Reference)
    negate: bool = False,
) -> dict:
    """
    Query v_gl for given GL patterns, optionally filtered by cost center prefix.
    Returns {month: amount}.

    Dual-filter (for RM GL 541x): CC LIKE prefix OR (CC IS NULL AND Reference LIKE prefix)
    """
    excl_ph = _in_clause(GL_EXCL_INTS)

    gl_conds = " OR ".join([f"CAST(\"G/L Account\" AS VARCHAR) LIKE '{p}'" for p in gl_like])
    conds = [
        "CAST(Year AS INTEGER) = ?",
        f"CAST(Month AS INTEGER) IN {_in_clause(months)}",
        f"({gl_conds})",
        f"CAST(CAST(\"G/L Account\" AS DOUBLE) AS BIGINT) NOT IN {excl_ph}",
    ]
    params: list = [year] + months + GL_EXCL_INTS

    if cc_like:
        if use_dual_filter:
            cc_or = " OR ".join([f"CAST(\"Cost Center\" AS VARCHAR) LIKE ?" for _ in cc_like])
            ref_or = " OR ".join([f"CAST(Reference AS VARCHAR) LIKE ?" for _ in cc_like])
            conds.append(
                f"({cc_or} OR (\"Cost Center\" IS NULL AND ({ref_or})))"
            )
            params += [f"{p}" for p in cc_like] + [f"{p}" for p in cc_like]
        else:
            cc_or = " OR ".join([f"CAST(\"Cost Center\" AS VARCHAR) LIKE ?" for _ in cc_like])
            conds.append(f"({cc_or})")
            params += [f"{p}" for p in cc_like]

    sign = "-1 *" if negate else ""
    where = " AND ".join(conds)
    try:
        df = query_df(
            f"""
            SELECT CAST(Month AS INTEGER) AS month,
                   {sign} SUM(Net_Amount) AS amount
            FROM v_gl
            WHERE {where}
            GROUP BY month ORDER BY month
            """,
            params,
        )
        return _to_month_dict(df, "amount")
    except Exception:
        return _zero_months(months)


def _rm_plant(year: int, months: list[int], cc_prefix: str, include_5411020: bool = False) -> dict:
    """RM cost for one plant. GI = 5411010 only; A1/A2 = 5411010+5411020."""
    gl_like = ["5411010%"]
    if include_5411020:
        gl_like.append("5411020%")
    return _gl_monthly(year, months, gl_like, [f"{cc_prefix}%"], use_dual_filter=True)


def _conv_plant(year: int, months: list[int], cc_prefix: str) -> dict:
    """Conversion cost for one plant: GL 55x-59x filtered by CC prefix."""
    return _gl_monthly(
        year, months,
        ["55%", "56%", "57%", "58%", "591%", "592%", "593%", "599%"],
        [f"{cc_prefix}%"],
        use_dual_filter=False,
    )


def _internal_rm_elim(year: int, months: list[int]) -> dict:
    """
    GL 5411020 consumed by A1+A2 — represents GI coil transferred internally.
    Returned as NEGATIVE to deduct from consolidated RM total.
    Avoids double-counting GI cost (GI line already captures full production cost).
    """
    return _gl_monthly(
        year, months,
        ["5411020%"],
        ["11%", "12%"],
        use_dual_filter=True,
        negate=True,  # return negative
    )


def _scrap_income(year: int, months: list[int]) -> dict:
    """Scrap/by-product sales income from GL 4211xxx (stored negative in GL → negate)."""
    return _gl_monthly(year, months, ["4211%"], None, negate=True)


def _transport(year: int, months: list[int]) -> dict:
    """Transport expense GL 6111030."""
    return _gl_monthly(year, months, ["6111030%"], None)


def _claims(year: int, months: list[int]) -> dict:
    """Customer claim expenses GL 4112xxx (stored as negative credits → negate to positive cost)."""
    return _gl_monthly(year, months, ["4112%"], None, negate=True)


def _interest(year: int, months: list[int]) -> dict:
    """Finance cost / interest GL 811xxx."""
    return _gl_monthly(year, months, ["811%"], None)


def _sum_dicts(*dicts: dict) -> dict:
    """Element-wise sum of multiple month dicts."""
    result: dict = {}
    for d in dicts:
        for m, v in d.items():
            result[m] = round(result.get(m, 0.0) + v, 2)
    return result


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/amc-conclusion")
def get_amc_conclusion(
    year: int = Query(2026, ge=2024, le=2030),
):
    """
    Consolidated monthly P&L for AMC (GI+A1+A2) — mirrors Conclusion sheet.

    Columns: Jan-May actual (available months), Jun-Dec = null
    All amounts in THB.
    """
    # Determine available months (Jan-May for 2026; full year otherwise)
    months = list(range(1, 6)) if year == 2026 else list(range(1, 13))

    # ── Revenue ──────────────────────────────────────────────────────────────
    revenue    = _revenue_monthly(year, months)
    scrap_inc  = _scrap_income(year, months)
    total_rev  = _sum_dicts(revenue, scrap_inc)

    # ── RM Cost ──────────────────────────────────────────────────────────────
    rm_gi     = _rm_plant(year, months, cc_prefix="13", include_5411020=False)
    rm_a1     = _rm_plant(year, months, cc_prefix="11", include_5411020=True)
    rm_a2     = _rm_plant(year, months, cc_prefix="12", include_5411020=True)
    rm_elim   = _internal_rm_elim(year, months)   # negative

    rm_total  = _sum_dicts(rm_gi, rm_a1, rm_a2, rm_elim)

    # ── Conversion Cost ──────────────────────────────────────────────────────
    conv_gi   = _conv_plant(year, months, cc_prefix="13")
    conv_a1   = _conv_plant(year, months, cc_prefix="11")
    conv_a2   = _conv_plant(year, months, cc_prefix="12")
    conv_total = _sum_dicts(conv_gi, conv_a1, conv_a2)

    # ── Other Costs ──────────────────────────────────────────────────────────
    transport  = _transport(year, months)
    claims     = _claims(year, months)
    interest   = _interest(year, months)

    # ── Totals ───────────────────────────────────────────────────────────────
    total_cost = _sum_dicts(rm_total, conv_total, transport, claims, interest)
    gross_profit = {m: round(total_rev.get(m, 0) - total_cost.get(m, 0), 2) for m in months}
    gp_margin = {
        m: round(gross_profit[m] / total_rev[m] * 100, 2) if total_rev.get(m) else 0.0
        for m in months
    }

    # ── YTD ──────────────────────────────────────────────────────────────────
    def ytd(d: dict) -> float:
        return round(sum(d.get(m, 0) for m in months), 2)

    ytd_rev  = ytd(total_rev)
    ytd_cost = ytd(total_cost)
    ytd_gp   = round(ytd_rev - ytd_cost, 2)
    ytd_margin = round(ytd_gp / ytd_rev * 100, 2) if ytd_rev else 0.0

    return {
        "status": "ok",
        "year":   year,
        "months": months,
        "revenue": {
            "sales":      revenue,
            "scrap":      scrap_inc,
            "total":      total_rev,
        },
        "rm": {
            "gi":           rm_gi,
            "a1":           rm_a1,
            "a2":           rm_a2,
            "internal_elim": rm_elim,   # negative values
            "total":        rm_total,
        },
        "conv": {
            "gi":    conv_gi,
            "a1":    conv_a1,
            "a2":    conv_a2,
            "total": conv_total,
        },
        "transport":   transport,
        "claims":      claims,
        "interest":    interest,
        "total_cost":  total_cost,
        "gross_profit": gross_profit,
        "gp_margin_pct": gp_margin,
        "ytd": {
            "revenue":      ytd_rev,
            "rm_total":     ytd(rm_total),
            "conv_total":   ytd(conv_total),
            "transport":    ytd(transport),
            "claims":       ytd(claims),
            "interest":     ytd(interest),
            "total_cost":   ytd_cost,
            "gross_profit": ytd_gp,
            "gp_margin_pct": ytd_margin,
        },
    }
