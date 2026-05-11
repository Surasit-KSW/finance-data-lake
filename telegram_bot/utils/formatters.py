"""
telegram_bot/utils/formatters.py
=================================
Format API data into Telegram-friendly text (plain text, not MarkdownV2).
All formatters return plain strings safe for send_message without parse_mode.

Telegram max message size = 4096 chars. Use split_message() for long output.
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime
from typing import Any
import pandas as pd


# ── Helpers ───────────────────────────────────────────────────────────────────

def _thb(value: Any, decimals: int = 0) -> str:
    """Format number as Thai Baht string."""
    try:
        v = float(value)
        if decimals == 0:
            return f"{v:,.0f}"
        return f"{v:,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Split long text at newlines so each chunk fits in one Telegram message."""
    if len(text) <= limit:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


# ── Health ────────────────────────────────────────────────────────────────────

def format_health(health: dict) -> str:
    status = health.get("status", "unknown")
    icon = "OK" if status == "ok" else "DOWN"
    lines = [
        f"[{icon}] Finance Data Lake API",
        f"Status  : {status}",
        f"Version : {health.get('version', 'n/a')}",
        f"DB      : {health.get('db_backend', health.get('database', 'n/a'))}",
    ]
    views = health.get("duckdb_views", [])
    if views:
        lines.append(f"Views   : {', '.join(views[:8])}")
    ts = health.get("timestamp", "")
    if ts:
        lines.append(f"Time    : {ts[:19]}")
    return "\n".join(lines)


# ── ETL ───────────────────────────────────────────────────────────────────────

def format_etl_status(run: dict) -> str:
    status = run.get("status", "unknown")
    icon = {"running": "...", "success": "OK", "failed": "FAIL"}.get(status, "?")
    lines = [
        f"[{icon}] ETL Run #{run.get('run_id', run.get('id', '?'))}",
        f"Domain  : {run.get('domain', 'all')}",
        f"Status  : {status}",
    ]
    if run.get("started_at"):
        lines.append(f"Started : {str(run['started_at'])[:19]}")
    if run.get("finished_at"):
        lines.append(f"Finished: {str(run['finished_at'])[:19]}")
    if run.get("rows_out"):
        lines.append(f"Rows out: {_thb(run['rows_out'])}")
    if run.get("error_msg"):
        lines.append(f"Error   : {run['error_msg'][:200]}")
    return "\n".join(lines)


def format_etl_runs(runs: list[dict]) -> str:
    if not runs:
        return "No ETL runs found."
    lines = ["Recent ETL Runs:", ""]
    for r in runs[:5]:
        status = r.get("status", "?")
        icon = {"running": "...", "success": "OK", "failed": "FAIL"}.get(status, "?")
        domain = r.get("domain", "all")
        started = str(r.get("started_at", ""))[:16]
        lines.append(f"  [{icon}] #{r.get('id', '?')} {domain} — {started}")
    return "\n".join(lines)


# ── P&L ───────────────────────────────────────────────────────────────────────

def format_pnl(pnl: dict, year: int | None = None) -> str:
    if not pnl:
        return "P&L data not available."
    title = f"P&L Statement {year or ''}"
    sep = "-" * 38
    lines = [title, sep]

    def row(label: str, value: Any, indent: int = 0) -> str:
        prefix = "  " * indent
        return f"{prefix}{label:<26}{_thb(value):>12}"

    revenue = pnl.get("revenue", 0)
    cogs = pnl.get("cogs", 0)
    gross_profit = pnl.get("gross_profit", 0)
    sga = pnl.get("sga", 0)
    ebit = pnl.get("ebit", 0)
    finance_cost = pnl.get("finance_cost", 0)
    ebt = pnl.get("ebt", 0)
    tax = pnl.get("tax", 0)
    net_income = pnl.get("net_income", 0)

    lines += [
        row("Revenue", revenue),
        row("COGS", cogs, 1),
        sep,
        row("Gross Profit", gross_profit),
        row("Gross Margin", _pct(pnl.get("gross_margin_pct", 0)), 1),
        row("SG&A", sga, 1),
        sep,
        row("EBIT", ebit),
        row("EBIT Margin", _pct(pnl.get("ebit_margin_pct", 0)), 1),
        row("Finance Cost", finance_cost, 1),
        sep,
        row("EBT", ebt),
        row("Tax", tax, 1),
        sep,
        row("Net Income", net_income),
        row("Net Margin", _pct(pnl.get("net_margin_pct", 0)), 1),
    ]
    lines.append(sep)
    lines.append("(THB)")
    return "\n".join(lines)


def format_pnl_compare(data: dict) -> str:
    if not data:
        return "Comparison data not available."
    y1 = data.get("year1", "Y1")
    y2 = data.get("year2", "Y2")
    pnl1 = data.get("pnl1", {})
    pnl2 = data.get("pnl2", {})

    sep = "-" * 54
    lines = [f"P&L Comparison  {y1} vs {y2}", sep]
    lines.append(f"{'':26}{'':>12}{'':>12}{'Var%':>6}")
    lines.append(sep)

    def cmp_row(label: str, k: str) -> str:
        v1 = pnl1.get(k, 0)
        v2 = pnl2.get(k, 0)
        try:
            var_pct = (float(v2) - float(v1)) / abs(float(v1)) * 100 if v1 else 0
            var_str = f"{var_pct:+.1f}%"
        except Exception:
            var_str = "n/a"
        return f"{label:<26}{_thb(v1):>12}{_thb(v2):>12}{var_str:>6}"

    for label, key in [
        ("Revenue", "revenue"), ("Gross Profit", "gross_profit"),
        ("EBIT", "ebit"), ("Net Income", "net_income"),
    ]:
        lines.append(cmp_row(label, key))
    lines.append(sep)
    lines.append("(THB)")
    return "\n".join(lines)


# ── KPI ───────────────────────────────────────────────────────────────────────

def format_kpi(kpi: dict, year: int | None = None) -> str:
    if not kpi:
        return "KPI data not available."
    sep = "-" * 30
    lines = [f"KPI Dashboard {year or ''}", sep]
    for label, key, fmt in [
        ("Gross Margin", "gross_margin_pct", "pct"),
        ("EBIT Margin", "ebit_margin_pct", "pct"),
        ("Net Margin", "net_margin_pct", "pct"),
        ("DSO (days)", "dso", "num"),
        ("Revenue Growth", "revenue_growth_pct", "pct"),
    ]:
        v = kpi.get(key, "n/a")
        val_str = _pct(v) if fmt == "pct" and v != "n/a" else (_thb(v, 1) if v != "n/a" else "n/a")
        lines.append(f"  {label:<20} {val_str:>8}")
    lines.append(sep)
    return "\n".join(lines)


# ── Sales ─────────────────────────────────────────────────────────────────────

def format_sales(df: pd.DataFrame, year: int | None = None) -> str:
    if df.empty:
        return f"No sales data for {year}."
    lines = [f"Sales Summary {year or ''}", "-" * 40]
    # Try to find month and total columns
    month_col = next((c for c in df.columns if "month" in c.lower()), None)
    total_col = next((c for c in df.columns if "total" in c.lower() or "revenue" in c.lower() or "amount" in c.lower()), None)
    if month_col and total_col:
        total = df[total_col].sum()
        lines.append(f"{'Month':<10}{'Amount':>16}")
        lines.append("-" * 28)
        for _, r in df.iterrows():
            lines.append(f"{str(r[month_col]):<10}{_thb(r[total_col]):>16}")
        lines.append("-" * 28)
        lines.append(f"{'Total':<10}{_thb(total):>16}")
    else:
        # Fallback: show first few columns
        lines.append(df.head(15).to_string(index=False))
    lines.append("(THB)")
    return "\n".join(lines)


# ── AR Aging ─────────────────────────────────────────────────────────────────

def format_ar_aging(df: pd.DataFrame, year: int | None = None, month: int | None = None) -> str:
    if df.empty:
        return "No AR aging data found."
    lines = [f"AR Aging {year or ''}/{month or ''}", "-" * 50]
    # Show top 15 rows with key columns
    key_cols = [c for c in df.columns if any(
        k in c.lower() for k in ["customer", "current", "30", "60", "90", "total", "overdue"]
    )]
    show_df = df[key_cols].head(15) if key_cols else df.head(15)
    lines.append(show_df.to_string(index=False, max_colwidth=20))
    if len(df) > 15:
        lines.append(f"... (+{len(df) - 15} more rows)")
    return "\n".join(lines)


# ── GL Accounts ───────────────────────────────────────────────────────────────

def format_gl_accounts(df: pd.DataFrame, year: int | None = None) -> str:
    if df.empty:
        return f"No GL accounts data for {year}."
    lines = [f"GL Accounts {year or ''} (top 20 by balance)", "-" * 50]
    balance_col = next((c for c in df.columns if "balance" in c.lower() or "amount" in c.lower()), None)
    acct_col = next((c for c in df.columns if "account" in c.lower() and "text" not in c.lower()), None)
    name_col = next((c for c in df.columns if "text" in c.lower() or "name" in c.lower()), None)
    if balance_col:
        top = df.nlargest(20, balance_col) if balance_col in df.columns else df.head(20)
    else:
        top = df.head(20)
    for _, r in top.iterrows():
        acct = str(r[acct_col])[:10] if acct_col else ""
        name = str(r[name_col])[:22] if name_col else ""
        bal = _thb(r[balance_col]) if balance_col else ""
        lines.append(f"  {acct:<10} {name:<22} {bal:>14}")
    lines.append("(THB)")
    return "\n".join(lines)


# ── Production Cost ───────────────────────────────────────────────────────────

def format_production_cost(df: pd.DataFrame, year: int | None = None) -> str:
    if df.empty:
        return f"No production cost data for {year}."
    lines = [f"Production Cost {year or ''}", "-" * 40]
    lines.append(df.head(20).to_string(index=False, max_colwidth=18))
    if len(df) > 20:
        lines.append(f"... (+{len(df) - 20} more rows)")
    lines.append("(THB)")
    return "\n".join(lines)


# ── Lake Status ───────────────────────────────────────────────────────────────

def format_lake_status(data: dict) -> str:
    views = data.get("views", data.get("data", {}))
    if not views:
        return "No view data available."
    lines = ["DuckDB View Status", "-" * 30]
    if isinstance(views, dict):
        for view, count in views.items():
            lines.append(f"  {view:<20} {_thb(count):>10} rows")
    elif isinstance(views, list):
        for item in views:
            if isinstance(item, dict):
                name = item.get("view", item.get("name", "?"))
                count = item.get("rows", item.get("count", "?"))
                lines.append(f"  {name:<20} {_thb(count):>10} rows")
    return "\n".join(lines)
