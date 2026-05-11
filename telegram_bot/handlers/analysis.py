"""
telegram_bot/handlers/analysis.py
===================================
AI-powered analysis handlers.

Commands:
  /variance [y1] [y2]  — Explain P&L variance drivers (Haiku, Sonnet if >30% delta)
  /forecast [year]     — Financial outlook forecast (always Sonnet)
  /ask [question]      — Direct AI question (model auto-selected)
  /clear               — Clear conversation history for this chat
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
from telegram_bot.services.ai_service import explain_variance, generate_forecast, answer_nl_query, clear_history
from telegram_bot.utils.summariser import summarise_pnl
from telegram_bot.utils.formatters import split_message

logger = logging.getLogger(__name__)
_CURRENT_YEAR = datetime.now().year


async def _send(update: Update, text: str) -> None:
    for chunk in split_message(text):
        await update.message.reply_text(chunk)


@require_auth
async def cmd_variance(update: Update, context: CallbackContext) -> None:
    """/variance [y1] [y2]  — Explain key P&L variance drivers."""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /variance [year1] [year2]\n"
            "Example: /variance 2024 2025"
        )
        return
    try:
        y1, y2 = int(args[0]), int(args[1])
    except ValueError:
        await update.message.reply_text("Years must be numbers. e.g. /variance 2024 2025")
        return

    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Analyzing P&L variance {y1} vs {y2}... (using AI)")

    try:
        pnl1, pnl2 = await lake.get_pnl(y1), await lake.get_pnl(y2)
    except LakeServiceError as e:
        await update.message.reply_text(f"[ERROR] Cannot fetch P&L data: {e}")
        return

    reply = await explain_variance(pnl1, pnl2, chat_id, y1, y2)
    await _send(update, reply)


@require_auth
async def cmd_forecast(update: Update, context: CallbackContext) -> None:
    """/forecast [year]  — Financial outlook (always uses Sonnet)."""
    args = context.args or []
    try:
        base_year = int(args[0]) if args else _CURRENT_YEAR - 1
    except ValueError:
        base_year = _CURRENT_YEAR - 1

    target_year = base_year + 1
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Generating forecast for {target_year} based on {base_year-1}–{base_year} data... (Sonnet)"
    )

    try:
        pnl_prev = await lake.get_pnl(base_year - 1)
        pnl_curr = await lake.get_pnl(base_year)
    except LakeServiceError as e:
        await update.message.reply_text(f"[ERROR] Cannot fetch P&L data: {e}")
        return

    summaries = [
        f"Year {base_year - 1}:\n{summarise_pnl(pnl_prev)}",
        f"Year {base_year}:\n{summarise_pnl(pnl_curr)}",
    ]
    reply = await generate_forecast(chat_id, summaries, target_year)
    await _send(update, reply)


@require_auth
async def cmd_ask(update: Update, context: CallbackContext) -> None:
    """/ask [question]  — Direct AI question without data context."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /ask [your question]\n"
            "Example: /ask What is DSO and how do we improve it?"
        )
        return
    question = " ".join(args)
    chat_id = update.effective_chat.id
    await update.message.reply_text("Thinking...")
    reply = await answer_nl_query(chat_id, question)
    await _send(update, reply)


@require_auth
async def cmd_clear_history(update: Update, context: CallbackContext) -> None:
    """/clear  — Clear AI conversation history for this chat."""
    chat_id = update.effective_chat.id
    clear_history(chat_id)
    await update.message.reply_text(
        "Conversation history cleared. "
        "I'll start fresh without context from previous messages."
    )
