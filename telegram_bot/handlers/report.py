"""
telegram_bot/handlers/report.py
=================================
/report command — export full reports to Google Drive (Sheets/Docs).
Falls back to sending formatted text if Drive is not configured.

Usage:
  /report pnl [year]        — P&L to Google Sheets
  /report sales [year]      — Sales summary to Sheets
  /report ar [year] [month] — AR aging to Sheets
  /report kpi [year]        — KPI summary to Sheets
  /report gl [year]         — GL accounts to Sheets
  /report forecast [year]   — AI forecast to Google Docs
"""
import sys
import logging
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from telegram import Update
from telegram.ext import CallbackContext

from telegram_bot.security import require_auth
from telegram_bot.services.lake_service import lake, LakeServiceError
from telegram_bot.services.drive_service import drive, DriveServiceError
from telegram_bot.services.ai_service import generate_forecast
from telegram_bot.utils.summariser import summarise_pnl
from telegram_bot.utils.formatters import (
    format_pnl, format_sales, format_ar_aging,
    format_kpi, format_gl_accounts, split_message,
)

logger = logging.getLogger(__name__)
_CURRENT_YEAR = datetime.now().year

_REPORT_TYPES = {"pnl", "sales", "ar", "kpi", "gl", "forecast"}

_USAGE = (
    "Usage: /report [type] [year] [month?]\n\n"
    "Types: pnl, sales, ar, kpi, gl, forecast\n"
    "Examples:\n"
    "  /report pnl 2025\n"
    "  /report sales 2025\n"
    "  /report ar 2025 12\n"
    "  /report forecast 2025"
)


async def _send(update: Update, text: str) -> None:
    for chunk in split_message(text):
        await update.message.reply_text(chunk)


@require_auth
async def cmd_report(update: Update, context: CallbackContext) -> None:
    """/report [type] [year] [month?]"""
    args = context.args or []
    if not args:
        await update.message.reply_text(_USAGE)
        return

    report_type = args[0].lower()
    if report_type not in _REPORT_TYPES:
        await update.message.reply_text(
            f"Unknown report type '{report_type}'.\n{_USAGE}"
        )
        return

    try:
        year = int(args[1]) if len(args) > 1 else _CURRENT_YEAR - 1
        month = int(args[2]) if len(args) > 2 else datetime.now().month
    except ValueError:
        await update.message.reply_text("Year/month must be numbers.\n" + _USAGE)
        return

    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"Preparing {report_type.upper()} report for {year}..."
        + ("\n(Will export to Google Drive)" if drive else "")
    )

    try:
        # ── P&L ──────────────────────────────────────────────────────────────
        if report_type == "pnl":
            pnl = await lake.get_pnl(year)
            if drive:
                url = await drive.upload_pnl(pnl, f"PnL_{year}", year)
                await update.message.reply_text(f"P&L {year} exported to Google Sheets:\n{url}")
            else:
                await _send(update, format_pnl(pnl, year))

        # ── Sales ─────────────────────────────────────────────────────────────
        elif report_type == "sales":
            df = await lake.get_sales(year)
            if drive:
                url = await drive.upload_dataframe(df, f"Sales_{year}")
                await update.message.reply_text(f"Sales {year} exported to Google Sheets:\n{url}")
            else:
                await _send(update, format_sales(df, year))

        # ── AR ────────────────────────────────────────────────────────────────
        elif report_type == "ar":
            df = await lake.get_ar_aging(year, month)
            if drive:
                url = await drive.upload_dataframe(df, f"AR_Aging_{year}_{month:02d}")
                await update.message.reply_text(f"AR Aging {year}/{month:02d} exported:\n{url}")
            else:
                await _send(update, format_ar_aging(df, year, month))

        # ── KPI ───────────────────────────────────────────────────────────────
        elif report_type == "kpi":
            kpi_data = await lake.get_kpi(year)
            if drive:
                import pandas as pd
                df = pd.DataFrame([{"Metric": k, "Value": v} for k, v in kpi_data.items()])
                url = await drive.upload_dataframe(df, f"KPI_{year}")
                await update.message.reply_text(f"KPI {year} exported to Sheets:\n{url}")
            else:
                await _send(update, format_kpi(kpi_data, year))

        # ── GL ────────────────────────────────────────────────────────────────
        elif report_type == "gl":
            df = await lake.get_gl_accounts(year)
            if drive:
                url = await drive.upload_dataframe(df, f"GL_Accounts_{year}")
                await update.message.reply_text(f"GL Accounts {year} exported to Sheets:\n{url}")
            else:
                await _send(update, format_gl_accounts(df, year))

        # ── Forecast ──────────────────────────────────────────────────────────
        elif report_type == "forecast":
            pnl_prev = await lake.get_pnl(year - 1)
            pnl_curr = await lake.get_pnl(year)
            summaries = [
                f"Year {year - 1}:\n{summarise_pnl(pnl_prev)}",
                f"Year {year}:\n{summarise_pnl(pnl_curr)}",
            ]
            forecast_text = await generate_forecast(chat_id, summaries, year + 1)
            if drive:
                content = f"Financial Forecast for {year + 1}\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{forecast_text}"
                url = await drive.upload_text(content, f"Forecast_{year + 1}")
                await update.message.reply_text(f"Forecast exported to Google Docs:\n{url}")
            else:
                await _send(update, f"Forecast for {year + 1}:\n\n{forecast_text}")

    except LakeServiceError as e:
        await update.message.reply_text(f"[ERROR] Data fetch failed: {e}")
    except DriveServiceError as e:
        await update.message.reply_text(f"[ERROR] Drive export failed: {e}")
    except Exception as e:
        logger.exception("Unexpected error in cmd_report")
        await update.message.reply_text(f"[ERROR] Unexpected error: {e}")
