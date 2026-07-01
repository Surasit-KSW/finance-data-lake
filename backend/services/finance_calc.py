"""
services/finance_calc.py — P&L calculation from REAL GL data (no dummy numbers)

SAP sign convention:
  Revenue (4.*) → credit = stored as NEGATIVE → flip sign → positive revenue
  COGS   (5.*) → debit  = stored as POSITIVE → cost is positive
  SGA    (6.*, 7.*) → debit = POSITIVE
  Finance Cost (8.*) → debit = POSITIVE
  Tax    (9.*) → debit = POSITIVE (usually near zero if not recorded in GL)
"""
from backend.services.db_service import query_df


def get_pnl(year: int) -> dict:
    """
    Build P&L statement for a given year from v_gl_summary.
    Returns dict with revenue, cogs, expenses, metrics.
    """
    df = query_df(
        """
        SELECT GL_Group, "G/L Account", GL_Name, SUM(Net_Amount) AS amount
        FROM v_gl_summary
        WHERE CAST("Year" AS INTEGER) = ?
        GROUP BY GL_Group, "G/L Account", GL_Name
        ORDER BY GL_Group, "G/L Account"
        """,
        [year],
    )

    if df.empty:
        return {"error": f"No GL data found for year {year}"}

    # Group amounts by GL_Group
    totals: dict[str, float] = df.groupby("GL_Group")["amount"].sum().to_dict()

    # Revenue: negative in SAP → flip sign
    revenue_raw   = totals.get("4. Revenue", 0.0)
    revenue_total = -revenue_raw  # now positive

    cogs_total      = totals.get("5. COGS", 0.0)
    selling_total   = totals.get("6. Selling Exp", 0.0)
    admin_total     = totals.get("7. Admin Exp", 0.0)
    finance_cost    = totals.get("8. Finance Cost", 0.0)
    tax_total       = totals.get("9. Tax", 0.0)

    gross_profit    = revenue_total - cogs_total
    opex_total      = selling_total + admin_total
    ebit            = gross_profit - opex_total
    ebt             = ebit - finance_cost
    net_income      = ebt - tax_total

    safe_rev = revenue_total if revenue_total != 0 else 1

    # Account-level breakdown for Revenue and COGS
    rev_accounts  = _accounts_for_group(df, "4. Revenue",  flip_sign=True)
    cogs_accounts = _accounts_for_group(df, "5. COGS",     flip_sign=False)

    return {
        "year": year,
        "revenue": {
            "total":    round(revenue_total, 2),
            "accounts": rev_accounts,
        },
        "cogs": {
            "total":    round(cogs_total, 2),
            "accounts": cogs_accounts,
        },
        "gross_profit": round(gross_profit, 2),
        "opex": {
            "selling":  round(selling_total, 2),
            "admin":    round(admin_total, 2),
            "total":    round(opex_total, 2),
        },
        "ebit":         round(ebit, 2),
        "finance_cost": round(finance_cost, 2),
        "ebt":          round(ebt, 2),
        "tax":          round(tax_total, 2),
        "net_income":   round(net_income, 2),
        "metrics": {
            "gross_margin_pct":  round(gross_profit / safe_rev * 100, 2),
            "ebit_margin_pct":   round(ebit / safe_rev * 100, 2),
            "net_margin_pct":    round(net_income / safe_rev * 100, 2),
            "opex_ratio_pct":    round(opex_total / safe_rev * 100, 2),
            "cogs_ratio_pct":    round(cogs_total / safe_rev * 100, 2),
        },
    }


def get_pnl_yoy(year1: int, year2: int) -> dict:
    """Compare two years side-by-side with variance."""
    p1 = get_pnl(year1)
    p2 = get_pnl(year2)

    if "error" in p1 or "error" in p2:
        return {"error": "One or both years have no GL data"}

    def var(a: float, b: float) -> dict:
        diff = b - a
        pct  = (diff / abs(a) * 100) if a != 0 else None
        return {"y1": a, "y2": b, "diff": round(diff, 2),
                "pct": round(pct, 2) if pct is not None else None}

    return {
        "year1": year1,
        "year2": year2,
        "revenue":      var(p1["revenue"]["total"],  p2["revenue"]["total"]),
        "cogs":         var(p1["cogs"]["total"],     p2["cogs"]["total"]),
        "gross_profit": var(p1["gross_profit"],      p2["gross_profit"]),
        "opex":         var(p1["opex"]["total"],     p2["opex"]["total"]),
        "ebit":         var(p1["ebit"],              p2["ebit"]),
        "net_income":   var(p1["net_income"],        p2["net_income"]),
        "gross_margin": var(p1["metrics"]["gross_margin_pct"],
                            p2["metrics"]["gross_margin_pct"]),
        "net_margin":   var(p1["metrics"]["net_margin_pct"],
                            p2["metrics"]["net_margin_pct"]),
    }


def get_kpi(year: int) -> dict:
    """Key financial ratios from real GL + Sales data."""
    pnl = get_pnl(year)
    if "error" in pnl:
        return pnl

    # DSO from Sales data
    dso = _calc_dso(year)

    return {
        "year":              year,
        "revenue":           pnl["revenue"]["total"],
        "gross_profit":      pnl["gross_profit"],
        "net_income":        pnl["net_income"],
        "gross_margin_pct":  pnl["metrics"]["gross_margin_pct"],
        "ebit_margin_pct":   pnl["metrics"]["ebit_margin_pct"],
        "net_margin_pct":    pnl["metrics"]["net_margin_pct"],
        "opex_ratio_pct":    pnl["metrics"]["opex_ratio_pct"],
        "cogs_ratio_pct":    pnl["metrics"]["cogs_ratio_pct"],
        "dso_days":          dso,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _accounts_for_group(df, gl_group: str, flip_sign: bool) -> list[dict]:
    sub = df[df["GL_Group"] == gl_group].copy()
    if flip_sign:
        sub["amount"] = -sub["amount"]
    return [
        {
            "account": row["G/L Account"],
            "name":    row["GL_Name"],
            "amount":  round(row["amount"], 2),
        }
        for _, row in sub.iterrows()
    ]


def _calc_dso(year: int) -> float | None:
    """
    DSO = (Ending AR / Annual Revenue) * 365
    AR จาก v_gl (GL Account ขึ้นต้น 12*) ณ สิ้นปี
    """
    try:
        # AR balance = net debit balance of accounts starting with 12
        ar_row = query_df(
            """
            SELECT SUM("Company Code Currency Value") AS ar_balance
            FROM v_gl
            WHERE company_code = ?
              AND CAST(Year AS INTEGER) = ?
              AND "G/L Account" LIKE '12%'
            """,
            ["1000", year],
        )
        ar_balance = float(ar_row["ar_balance"].iloc[0] or 0)

        pnl = get_pnl(year)
        revenue = pnl.get("revenue", {}).get("total", 0)
        if revenue == 0:
            return None

        dso = abs(ar_balance) / revenue * 365
        return round(dso, 1)
    except Exception:
        return None
