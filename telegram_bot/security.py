"""
telegram_bot/security.py
========================
Access control: whitelist-based auth via TELEGRAM_ALLOWED_USERS.
If the whitelist is empty, ALL requests are denied.
"""
import logging
from functools import wraps
from typing import Callable

from telegram import Update
from telegram.ext import CallbackContext

from telegram_bot.config import settings

logger = logging.getLogger(__name__)


def is_allowed(chat_id: int) -> bool:
    """Return True if chat_id is in the whitelist. Empty whitelist → deny all."""
    allowed = settings.allowed_user_ids
    return chat_id in allowed


def require_auth(func: Callable) -> Callable:
    """
    Async decorator for python-telegram-bot handlers.
    Sends "Access denied" and returns early if the sender is not whitelisted.

    Usage:
        @require_auth
        async def cmd_health(update: Update, context: CallbackContext) -> None:
            ...
    """
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None or not is_allowed(chat_id):
            logger.warning("Unauthorized access attempt from chat_id=%s", chat_id)
            if update.message:
                await update.message.reply_text(
                    "Access denied. This bot is restricted to authorized users.\n"
                    "Contact the system administrator to request access."
                )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
