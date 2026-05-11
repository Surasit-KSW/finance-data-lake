"""
telegram_bot/utils/summariser.py
=================================
Data reduction functions — reduce DataFrames and dicts to compact text
BEFORE sending to Claude. Critical for token cost control.

Target: each summary ≤ 200 tokens (≈ 150 words / 800 chars).
Never pass raw DataFrames or full account-level breakdowns to Claude.
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from typing import Any
import pandas as pd


def _thb(v: Any) -> str:
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return str(v)


def _pct(v: Any) -> str:
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return str(v)


def summarise_pnl(pnl: dict) -> str:
    """
    Reduce full P&L dict to key metrics only.
    Output: ~100-150 tokens covering revenue, margins, net income.
    """
    if not pnl:
        return "P&L data unavailable."
    lines = [
        f"Revenue: {_thb(pnl.get('revenue', 0))} THB",
        f"Gross Profit: {_thb(pnl.get('gross_profit', 0))} THB "
        f"(margin {_pct(pnl.get('gross_margin_pct', 0))})",
        f"EBIT: {_thb(pnl.get('ebit', 0))} THB "
        f"(margin {_pct(pnl.get('ebit_margin_pct', 0))})",
        f"Net Income: {_thb(pnl.get('net_income', 0))} THB "
        f"(margin {_pct(pnl.get('net_margin_pct', 0))})",
        f"COGS: {_thb(pnl.get('cogs', 0))} THB",
        f"SGA: {_thb(pnl.get('sga', 0))} THB",
        f"Finance Cost: {_thb(pnl.get('finance_cost', 0))} THB",
    ]
    return "\n".join(lines)


def summarise_pnl_compare(data: dict) -> str:
    """
    Reduce YoY P&L comparison to delta summary.
    Output: ~150 tokens.
    """
    if not data:
        return "Comparison data unavailable."
    y1 = data.get("year1", "Y1")
    y2 = data.get("year2", "Y2")
    p1 = data.get("pnl1", {})
    p2 = data.get("pnl2", {})

    def delta(k: str) -> str:
        v1, v2 = float(p1.get(k, 0)), float(p2.get(k, 0))
        d = v2 - v1
        pct = (d / abs(v1) * 100) if v1 else 0
        return f"{_thb(v2)} ({pct:+.1f}% vs {_thb(v1)})"

    lines = [
        f"P&L Comparison {y1} vs {y2}:",
        f"Revenue: {delta('revenue')}",
        f"Gross Profit: {delta('gross_profit')}",
        f"EBIT: {delta('ebit')}",
        f"Net Income: {delta('net_income')}",
        f"Gross Margin: {_pct(p2.get('gross_margin_pct',0))} vs {_pct(p1.get('gross_margin_pct',0))}",
    ]
    return "\n".join(lines)


def summarise_kpi(kpi: dict) -> str:
    """~60 tokens."""
    if not kpi:
        return "KPI data unavailable."
    lines = [
        f"Gross Margin: {_pct(kpi.get('gross_margin_pct', 0))}",
        f"EBIT Margin: {_pct(kpi.get('ebit_margin_pct', 0))}",
        f"Net Margin: {_pct(kpi.get('net_margin_pct', 0))}",
        f"DSO: {kpi.get('dso', 'n/a')} days",
        f"Revenue Growth: {_pct(kpi.get('revenue_growth_pct', 0))}",
    ]
    return "\n".join(lines)


def summarise_sales(df: pd.DataFrame, year: int | None = None) -> str:
    """
    Reduce monthly sales DataFrame to total + top products.
    Output: ~100 tokens.
    """
    if df is None or df.empty:
        return f"No sales data{f' for {year}' if year else ''}."

    amount_col = next(
        (c for c in df.columns if any(k in c.lower() for k in ["total", "amount", "revenue", "net"])),
        None
    )
    lines = [f"Sales Summary{f' {year}' if year else ''}:"]
    if amount_col:
        total = df[amount_col].sum()
        lines.append(f"Total Revenue: {_thb(total)} THB")
        # Top 3 product groups
        prod_col = next((c for c in df.columns if "product" in c.lower() or "group" in c.lower()), None)
        if prod_col:
            top = df.groupby(prod_col)[amount_col].sum().nlargest(3)
            lines.append("Top products:")
            for name, val in top.items():
                lines.append(f"  {name}: {_thb(val)} THB")
    else:
        lines.append(f"Rows: {len(df)}, Columns: {list(df.columns[:5])}")
    return "\n".join(lines)


def summarise_ar(df: pd.DataFrame) -> str:
    """
    Top 5 overdue + aging bucket totals.
    Output: ~80 tokens.
    """
    if df is None or df.empty:
        return "No AR data available."

    lines = ["AR Aging Summary:"]
    # Try to find bucket columns
    bucket_cols = [c for c in df.columns if any(
        k in c.lower() for k in ["current", "30", "60", "90", "total", "overdue"]
    )]
    if bucket_cols:
        totals = {c: df[c].sum() for c in bucket_cols if pd.api.types.is_numeric_dtype(df[c])}
        for col, val in totals.items():
            lines.append(f"  {col}: {_thb(val)} THB")
    lines.append(f"Total customers: {len(df)}")
    return "\n".join(lines)


def summarise_gl_accounts(df: pd.DataFrame, year: int | None = None) -> str:
    """
    Top 10 accounts by absolute balance.
    Output: ~80 tokens.
    """
    if df is None or df.empty:
        return f"No GL data{f' for {year}' if year else ''}."

    balance_col = next(
        (c for c in df.columns if "balance" in c.lower() or "amount" in c.lower()),
        None
    )
    lines = [f"GL Accounts{f' {year}' if year else ''}:"]
    lines.append(f"Total accounts: {len(df)}")
    if balance_col:
        total = df[balance_col].sum()
        lines.append(f"Total balance: {_thb(total)} THB")
        top = df.nlargest(5, balance_col)
        acct_col = next((c for c in df.columns if "account" in c.lower() and "text" not in c.lower()), None)
        for _, r in top.iterrows():
            acct = str(r[acct_col]) if acct_col else "?"
            lines.append(f"  {acct}: {_thb(r[balance_col])} THB")
    return "\n".join(lines)


def summarise_health(health: dict) -> str:
    """~30 tokens."""
    return (
        f"API: {health.get('status', 'unknown')}, "
        f"DB: {health.get('db_backend', health.get('database', 'n/a'))}, "
        f"Views: {len(health.get('duckdb_views', []))}"
    )


def truncate_for_context(text: str, max_chars: int = 800) -> str:
    """Hard truncate with ellipsis — last resort safety net."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 20] + "\n...[truncated]"
