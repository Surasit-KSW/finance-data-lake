"""
telegram_bot/handlers/data.py
==============================
Data command handlers — no AI cost.
All commands call the API, format the result, and send it back.
Large responses (>4000 chars) are automatically sent in chunks.

Commands:
  /pnl [year]
  /compare [y1] [y2]
  /sales [year]
  /ar [year] [month]
  /gl [year] [account?]
  /kpi [year]
  /cost [year] [month?]
  /tb [period]
"""
import sys
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime
import requests

from telegram import Update
from telegram.ext import CallbackContext

from telegram_bot.security import require_auth
from telegram_bot.services.lake_service import lake, LakeServiceError
from telegram_bot.utils.formatters import (
    format_pnl, format_pnl_compare, format_kpi,
    format_sales, format_ar_aging,
    format_gl_accounts, format_production_cost,
    split_message,
)

logger = logging.getLogger(__name__)

_CURRENT_YEAR = datetime.now().year


async def _send(update: Update, text: str) -> None:
    """Send text, splitting into chunks if needed."""
    for chunk in split_message(text, limit=4000):
        await update.message.reply_text(chunk)


# ── P&L ───────────────────────────────────────────────────────────────────────

@require_auth
async def cmd_pnl(update: Update, context: CallbackContext) -> None:
    """/pnl [year]  — P&L statement."""
    args = context.args or []
    try:
        year = int(args[0]) if args else _CURRENT_YEAR - 1
    except ValueError:
        await update.message.reply_text("Usage: /pnl [year]  e.g. /pnl 2025")
        return

    await update.message.reply_text(f"Fetching P&L for {year}...")
    try:
        pnl = await lake.get_pnl(year)
        text = format_pnl(pnl, year)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await _send(update, text)


# ── YoY Compare ───────────────────────────────────────────────────────────────

@require_auth
async def cmd_compare(update: Update, context: CallbackContext) -> None:
    """/compare [y1] [y2]  — P&L year-over-year comparison."""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /compare [year1] [year2]  e.g. /compare 2024 2025")
        return
    try:
        y1, y2 = int(args[0]), int(args[1])
    except ValueError:
        await update.message.reply_text("Years must be numbers. e.g. /compare 2024 2025")
        return

    await update.message.reply_text(f"Comparing P&L {y1} vs {y2}...")
    try:
        data = await lake.get_pnl_compare(y1, y2)
        text = format_pnl_compare(data)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await _send(update, text)


# ── Sales ─────────────────────────────────────────────────────────────────────

@require_auth
async def cmd_sales(update: Update, context: CallbackContext) -> None:
    """/sales [year]  — Monthly sales summary."""
    args = context.args or []
    try:
        year = int(args[0]) if args else _CURRENT_YEAR - 1
    except ValueError:
        await update.message.reply_text("Usage: /sales [year]  e.g. /sales 2025")
        return

    await update.message.reply_text(f"Fetching sales data for {year}...")
    try:
        df = await lake.get_sales(year)
        text = format_sales(df, year)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await _send(update, text)


# ── AR ────────────────────────────────────────────────────────────────────────

@require_auth
async def cmd_ar(update: Update, context: CallbackContext) -> None:
    """/ar [year] [month]  — AR aging report."""
    args = context.args or []
    now = datetime.now()
    try:
        year = int(args[0]) if len(args) > 0 else now.year
        month = int(args[1]) if len(args) > 1 else now.month
    except ValueError:
        await update.message.reply_text("Usage: /ar [year] [month]  e.g. /ar 2025 12")
        return

    await update.message.reply_text(f"Fetching AR aging {year}/{month:02d}...")
    try:
        df = await lake.get_ar_aging(year, month)
        text = format_ar_aging(df, year, month)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await _send(update, text)


# ── GL ────────────────────────────────────────────────────────────────────────

@require_auth
async def cmd_gl(update: Update, context: CallbackContext) -> None:
    """/gl [year] [account?]  — GL accounts overview or account transactions."""
    args = context.args or []
    try:
        year = int(args[0]) if args and args[0].isdigit() else _CURRENT_YEAR - 1
    except ValueError:
        year = _CURRENT_YEAR - 1

    # Check if second arg looks like an account code
    account = None
    if len(args) >= 2 and args[1].isdigit() and len(args[1]) >= 4:
        account = args[1]
    elif len(args) >= 1 and not args[0].isdigit():
        account = args[0]
        year = _CURRENT_YEAR - 1

    if account:
        await update.message.reply_text(f"Fetching GL transactions for account {account} ({year})...")
        try:
            df = await lake.get_gl_transactions(year=year, account=account, limit=50)
            if df.empty:
                text = f"No transactions found for account {account} in {year}."
            else:
                text = f"GL Transactions — Account {account} ({year})\n"
                text += "-" * 50 + "\n"
                text += df.head(20).to_string(index=False, max_colwidth=20)
                if len(df) > 20:
                    text += f"\n... (+{len(df) - 20} more rows)"
        except LakeServiceError as e:
            text = f"[ERROR] {e}"
    else:
        await update.message.reply_text(f"Fetching GL accounts for {year}...")
        try:
            df = await lake.get_gl_accounts(year)
            text = format_gl_accounts(df, year)
        except LakeServiceError as e:
            text = f"[ERROR] {e}"

    await _send(update, text)


# ── KPI ───────────────────────────────────────────────────────────────────────

@require_auth
async def cmd_kpi(update: Update, context: CallbackContext) -> None:
    """/kpi [year]  — Key financial ratios."""
    args = context.args or []
    try:
        year = int(args[0]) if args else _CURRENT_YEAR - 1
    except ValueError:
        await update.message.reply_text("Usage: /kpi [year]  e.g. /kpi 2025")
        return

    await update.message.reply_text(f"Fetching KPIs for {year}...")
    try:
        kpi = await lake.get_kpi(year)
        text = format_kpi(kpi, year)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await _send(update, text)


# ── Production Cost ───────────────────────────────────────────────────────────

@require_auth
async def cmd_cost(update: Update, context: CallbackContext) -> None:
    """/cost [year] [month?]  — Production cost summary."""
    args = context.args or []
    try:
        year = int(args[0]) if args else _CURRENT_YEAR
        month = int(args[1]) if len(args) > 1 else None
    except ValueError:
        await update.message.reply_text("Usage: /cost [year] [month?]  e.g. /cost 2026 3")
        return

    label = f"{year}/{month:02d}" if month else str(year)
    await update.message.reply_text(f"Fetching production cost for {label}...")
    try:
        df = await lake.get_production_cost(year, month)
        text = format_production_cost(df, year)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await _send(update, text)


# ── Trial Balance ─────────────────────────────────────────────────────────────

@require_auth
async def cmd_tb(update: Update, context: CallbackContext) -> None:
    """/tb [period]  — Trial Balance for a period (YYYY-MM-DD)."""
    args = context.args or []
    if not args:
        # List available periods
        await update.message.reply_text("Fetching available TB periods...")
        try:
            base = f"{lake._base}/api/v1/financial/tb"
            import asyncio
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(base, timeout=15)
            )
            data = resp.json()
            periods = data.get("periods", [])
            if not periods:
                text = "No Trial Balance periods available."
            else:
                lines = ["Available TB periods:"]
                for p in periods:
                    avail = "OK" if p.get("available") else "MISSING"
                    lines.append(f"  [{avail}] {p.get('period')} — {p.get('account_count', '?')} accounts")
                text = "\n".join(lines)
        except Exception as e:
            text = f"[ERROR] {e}"
        await _send(update, text)
        return

    period = args[0]
    await update.message.reply_text(f"Fetching Trial Balance for {period}...")
    try:
        import asyncio
        base = f"{lake._base}/api/v1/financial/tb/{period}"
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: requests.get(base, timeout=15)
        )
        data = resp.json().get("data", [])
        if not data:
            text = f"No TB data found for period {period}."
        else:
            import pandas as pd
            df = pd.DataFrame(data)
            text = f"Trial Balance — {period}\n"
            text += "-" * 50 + "\n"
            text += df.head(30).to_string(index=False, max_colwidth=25)
            if len(df) > 30:
                text += f"\n... (+{len(df) - 30} more accounts)"
    except Exception as e:
        text = f"[ERROR] {e}"
    await _send(update, text)
