"""
telegram_bot/router.py
=======================
Central message dispatcher for natural language (non-command) messages.

Routing decision tree:
  1. Security check → deny if not whitelisted
  2. Intent detection via keyword rules (zero AI cost)
     a. High-confidence + data domain → call data service directly
     b. High-confidence + analysis → call analysis handler
     c. Low-confidence or "unknown" → call ai_service with optional data context
"""
import sys
import logging
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from telegram import Update
from telegram.ext import CallbackContext

from telegram_bot.security import is_allowed
from telegram_bot.utils.intent import detect_intent
from telegram_bot.utils.formatters import split_message
from telegram_bot.services.lake_service import lake, LakeServiceError
from telegram_bot.services.ai_service import answer_nl_query
from telegram_bot.utils.summariser import (
    summarise_pnl, summarise_sales, summarise_ar,
    summarise_kpi, summarise_gl_accounts, truncate_for_context,
)

logger = logging.getLogger(__name__)
_CURRENT_YEAR = datetime.now().year


async def _send(update: Update, text: str) -> None:
    for chunk in split_message(text):
        await update.message.reply_text(chunk)


class BotRouter:
    """Handles all non-command text messages."""

    async def dispatch(self, update: Update, context: CallbackContext) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else None

        # Security check
        if chat_id is None or not is_allowed(chat_id):
            if update.message:
                await update.message.reply_text(
                    "Access denied. Use /start to get your chat ID and request access."
                )
            return

        text = update.message.text or ""
        if not text.strip():
            return

        intent = detect_intent(text)
        logger.info(
            "NL dispatch chat_id=%d intent=%s confidence=%s params=%s",
            chat_id, intent.intent, intent.confidence, intent.params
        )

        # High-confidence data intents → route directly (no AI)
        if intent.confidence == "high":
            handled = await self._route_data(update, intent)
            if handled:
                return

        # Analysis intents or low-confidence → AI with data context
        await self._route_ai(update, chat_id, text, intent)

    async def _route_data(self, update: Update, intent) -> bool:
        """
        Route high-confidence intent to data service.
        Returns True if handled, False if should fall through to AI.
        """
        params = intent.params
        year = params.get("year", _CURRENT_YEAR - 1)
        month = params.get("month", datetime.now().month)

        try:
            if intent.intent == "health":
                health = await lake.get_health()
                from telegram_bot.utils.formatters import format_health
                await _send(update, format_health(health))
                return True

            elif intent.intent in ("revenue", "pnl"):
                pnl = await lake.get_pnl(year)
                from telegram_bot.utils.formatters import format_pnl
                await _send(update, format_pnl(pnl, year))
                return True

            elif intent.intent == "sales":
                df = await lake.get_sales(year)
                from telegram_bot.utils.formatters import format_sales
                await _send(update, format_sales(df, year))
                return True

            elif intent.intent == "ar":
                df = await lake.get_ar_aging(year, month)
                from telegram_bot.utils.formatters import format_ar_aging
                await _send(update, format_ar_aging(df, year, month))
                return True

            elif intent.intent == "kpi":
                kpi = await lake.get_kpi(year)
                from telegram_bot.utils.formatters import format_kpi
                await _send(update, format_kpi(kpi, year))
                return True

            elif intent.intent == "gl":
                df = await lake.get_gl_accounts(year)
                from telegram_bot.utils.formatters import format_gl_accounts
                await _send(update, format_gl_accounts(df, year))
                return True

            elif intent.intent == "cost":
                df = await lake.get_production_cost(year, params.get("month"))
                from telegram_bot.utils.formatters import format_production_cost
                await _send(update, format_production_cost(df, year))
                return True

        except LakeServiceError as e:
            await _send(update, f"[ERROR] {e}")
            return True

        return False

    async def _route_ai(self, update: Update, chat_id: int, text: str, intent) -> None:
        """
        Route to Claude with appropriate data context pre-fetched.
        Fetches minimal data summary to keep tokens low.
        """
        params = intent.params
        year = params.get("year", _CURRENT_YEAR - 1)
        data_summary = ""

        # Pre-fetch relevant data for context
        try:
            if intent.intent in ("pnl", "revenue", "compare"):
                pnl = await lake.get_pnl(year)
                data_summary = f"P&L {year}:\n{summarise_pnl(pnl)}"

                # If multiple years mentioned, fetch both
                years = params.get("years", [])
                if len(years) >= 2:
                    pnl2 = await lake.get_pnl(years[0])
                    data_summary += f"\n\nP&L {years[0]}:\n{summarise_pnl(pnl2)}"

            elif intent.intent in ("sales", "revenue"):
                df = await lake.get_sales(year)
                data_summary = f"Sales {year}:\n{summarise_sales(df, year)}"

            elif intent.intent == "ar":
                df = await lake.get_ar_aging(year, params.get("month", datetime.now().month))
                data_summary = f"AR Aging:\n{summarise_ar(df)}"

            elif intent.intent == "kpi":
                kpi = await lake.get_kpi(year)
                data_summary = f"KPIs {year}:\n{summarise_kpi(kpi)}"

            elif intent.intent == "gl":
                df = await lake.get_gl_accounts(year)
                data_summary = f"GL Accounts {year}:\n{summarise_gl_accounts(df, year)}"

        except LakeServiceError as e:
            logger.warning("Could not fetch data context: %s", e)
            data_summary = f"(Data unavailable: {e})"

        # Safety: cap context size
        data_summary = truncate_for_context(data_summary, max_chars=800)

        await update.message.reply_text("Thinking...")
        reply = await answer_nl_query(chat_id, text, data_summary)
        await _send(update, reply)
