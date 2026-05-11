"""
telegram_bot/handlers/system.py
================================
System command handlers — no AI cost.

Commands:
  /start   - Welcome message + chat ID (for adding to whitelist)
  /help    - Full command reference
  /health  - API health check (cached 5 min)
  /status  - Alias for /health
  /etl     - Trigger ETL pipeline
  /refresh - Clear cache + trigger ETL refresh
  /cache   - Show cache statistics
"""
import sys
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from telegram import Update
from telegram.ext import CallbackContext

from telegram_bot.security import require_auth
from telegram_bot.services.lake_service import lake, LakeServiceError
from telegram_bot.utils.formatters import format_health, format_etl_status, format_etl_runs, format_lake_status

logger = logging.getLogger(__name__)

HELP_TEXT = """Finance Data Lake Bot — Command Reference

DATA COMMANDS (no AI cost)
  /health           API status + DuckDB views
  /pnl [year]       P&L statement (default: 2025)
  /compare Y1 Y2    YoY P&L comparison (e.g. /compare 2024 2025)
  /sales [year]     Monthly sales summary
  /ar [year] [mo]   AR aging (e.g. /ar 2025 12)
  /gl [year]        GL accounts overview
  /kpi [year]       Key financial ratios
  /cost [year]      Production cost summary

ETL / OPS
  /etl [domain]     Trigger ETL (all|sales|gl|ar|production)
  /etl status       Last 5 ETL runs
  /refresh          Clear cache + re-trigger ETL

AI ANALYSIS (uses Claude API — costs tokens)
  /variance Y1 Y2   Explain P&L variance drivers (Haiku)
  /forecast [year]  Financial outlook forecast (Sonnet)
  /report [type] [year]   Export full report to Google Sheets

Or just type a question in Thai or English!
Examples:
  กำไรปี 2025 เป็นเท่าไหร่?
  Why did revenue drop in Q3?
  Forecast sales for 2026"""


async def cmd_start(update: Update, context: CallbackContext) -> None:
    """No auth required — show chat ID so user can request access."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Finance Data Lake Bot\n"
        f"Your chat ID: {chat_id}\n\n"
        f"Send this ID to the administrator to request access.\n"
        f"Once authorized, use /help to see available commands."
    )


@require_auth
async def cmd_help(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(HELP_TEXT)


@require_auth
async def cmd_health(update: Update, context: CallbackContext) -> None:
    """GET /api/v1/health — cached 5 min."""
    await update.message.reply_text("Checking API health...")
    try:
        health = await lake.get_health()
        text = format_health(health)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await update.message.reply_text(text)


@require_auth
async def cmd_etl(update: Update, context: CallbackContext) -> None:
    """
    /etl              — trigger domain=all
    /etl sales        — trigger domain=sales
    /etl sales 2026   — trigger domain=sales year=2026
    /etl status       — show last 5 runs
    """
    args = context.args or []

    # /etl status
    if args and args[0].lower() == "status":
        try:
            runs = await lake.get_etl_runs(limit=5)
            text = format_etl_runs(runs)
        except LakeServiceError as e:
            text = f"[ERROR] {e}"
        await update.message.reply_text(text)
        return

    domain = args[0] if args else "all"
    year = args[1] if len(args) > 1 else None

    valid_domains = {"all", "sales", "gl", "ar", "production"}
    if domain not in valid_domains:
        await update.message.reply_text(
            f"Unknown domain '{domain}'. Valid: {', '.join(sorted(valid_domains))}"
        )
        return

    await update.message.reply_text(
        f"Triggering ETL pipeline...\nDomain: {domain}" + (f"\nYear: {year}" if year else "")
    )
    try:
        result = await lake.trigger_etl(domain=domain, year=year)
        text = format_etl_status(result)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await update.message.reply_text(text)


@require_auth
async def cmd_refresh(update: Update, context: CallbackContext) -> None:
    """Clear all cache entries, then trigger full ETL."""
    invalidated = await lake.invalidate_all()
    await update.message.reply_text(
        f"Cache cleared ({invalidated} entries removed).\nTriggering full ETL..."
    )
    try:
        result = await lake.trigger_etl(domain="all")
        text = format_etl_status(result)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await update.message.reply_text(text)


@require_auth
async def cmd_cache(update: Update, context: CallbackContext) -> None:
    """Show cache hit/miss statistics."""
    stats = lake.cache_stats()
    lines = [
        "Cache Statistics",
        f"  Keys cached : {stats['total_keys']}",
        f"  Hits        : {stats['hits']}",
        f"  Misses      : {stats['misses']}",
        f"  Hit rate    : {stats['hit_rate']}",
    ]
    await update.message.reply_text("\n".join(lines))


@require_auth
async def cmd_lake_status(update: Update, context: CallbackContext) -> None:
    """Show DuckDB view row counts."""
    try:
        data = await lake.get_lake_status()
        text = format_lake_status(data)
    except LakeServiceError as e:
        text = f"[ERROR] {e}"
    await update.message.reply_text(text)
