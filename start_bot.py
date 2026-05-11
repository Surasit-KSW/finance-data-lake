"""
start_bot.py
============
Finance Data Lake — Telegram Bot Entry Point

Run:
    python start_bot.py

Prerequisites:
    1. Add TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS to .env
    2. FastAPI server running: uvicorn backend.main:app --reload --port 8000
    3. Install deps: pip install -r requirements.txt
"""
import sys
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from telegram_bot.config import settings
from telegram_bot.handlers import system, data, analysis, report
from telegram_bot.router import BotRouter

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def build_app() -> Application:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to .env:\n"
            "  TELEGRAM_BOT_TOKEN=your_token_from_botfather"
        )

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    router = BotRouter()

    # ── System commands (no AI cost) ──────────────────────────────────────────
    app.add_handler(CommandHandler("start",   system.cmd_start))
    app.add_handler(CommandHandler("help",    system.cmd_help))
    app.add_handler(CommandHandler("health",  system.cmd_health))
    app.add_handler(CommandHandler("status",  system.cmd_health))
    app.add_handler(CommandHandler("etl",     system.cmd_etl))
    app.add_handler(CommandHandler("refresh", system.cmd_refresh))
    app.add_handler(CommandHandler("cache",   system.cmd_cache))
    app.add_handler(CommandHandler("lake",    system.cmd_lake_status))

    # ── Data commands (no AI cost) ────────────────────────────────────────────
    app.add_handler(CommandHandler("pnl",     data.cmd_pnl))
    app.add_handler(CommandHandler("compare", data.cmd_compare))
    app.add_handler(CommandHandler("sales",   data.cmd_sales))
    app.add_handler(CommandHandler("ar",      data.cmd_ar))
    app.add_handler(CommandHandler("gl",      data.cmd_gl))
    app.add_handler(CommandHandler("kpi",     data.cmd_kpi))
    app.add_handler(CommandHandler("cost",    data.cmd_cost))
    app.add_handler(CommandHandler("tb",      data.cmd_tb))

    # ── AI analysis (Claude Haiku/Sonnet) ─────────────────────────────────────
    app.add_handler(CommandHandler("variance", analysis.cmd_variance))
    app.add_handler(CommandHandler("forecast", analysis.cmd_forecast))
    app.add_handler(CommandHandler("ask",      analysis.cmd_ask))
    app.add_handler(CommandHandler("clear",    analysis.cmd_clear_history))

    # ── Report/export (Claude + Google Drive) ─────────────────────────────────
    app.add_handler(CommandHandler("report", report.cmd_report))

    # ── Catch-all: NL messages route through intent → AI pipeline ────────────
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, router.dispatch)
    )

    return app


if __name__ == "__main__":
    logger.info("Finance Data Lake Telegram Bot starting...")
    logger.info("API endpoint : %s", settings.DATA_LAKE_URL)
    logger.info("Drive enabled: %s", settings.drive_enabled)

    allowed = settings.allowed_user_ids
    if not allowed:
        logger.warning(
            "TELEGRAM_ALLOWED_USERS is empty — ALL access will be denied. "
            "Add your Telegram chat ID to .env to enable access. "
            "Use /start to find your chat ID."
        )
    else:
        logger.info("Allowed users: %s", allowed)

    app = build_app()
    logger.info("Bot polling for updates. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
