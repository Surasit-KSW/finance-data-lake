"""
telegram_bot/services/ai_service.py
=====================================
Claude API integration with token cost control.

Cost tiers:
  - claude-haiku:  simple Q&A, single-domain, variance (<30% delta)
  - claude-sonnet: forecast, multi-domain complex analysis, large delta variance

Per-user sliding conversation history (max 3 exchanges, cleared on restart).
Data summaries injected per-call — never pass raw DataFrames.
System prompt kept at ~50 tokens.
"""
import sys
import logging
import re
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import anthropic

from telegram_bot.config import settings

logger = logging.getLogger(__name__)

# ── System prompt (minimal — ~50 tokens) ──────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a financial analyst assistant for Asia Metal Company (AMC), a Thai steel manufacturer. "
    "Answer questions about P&L, GL, AR aging, Sales, Production cost, and KPIs. "
    "Respond in the same language the user uses (Thai or English). "
    "Be concise. Format numbers in THB with commas. Do not fabricate data."
)

# ── Conversation history ───────────────────────────────────────────────────────

class ConversationHistory:
    """Per-user sliding window of last N exchanges (in-process, reset on restart)."""

    def __init__(self, max_exchanges: int = 3):
        self._max = max_exchanges
        # chat_id → list of {role, content} dicts
        self._store: dict[int, list[dict]] = {}

    def add_user(self, chat_id: int, text: str) -> None:
        self._store.setdefault(chat_id, []).append({"role": "user", "content": text})
        self._trim(chat_id)

    def add_assistant(self, chat_id: int, text: str) -> None:
        self._store.setdefault(chat_id, []).append({"role": "assistant", "content": text})
        self._trim(chat_id)

    def get_messages(self, chat_id: int) -> list[dict]:
        """Return last N exchanges (user+assistant pairs)."""
        msgs = self._store.get(chat_id, [])
        # Keep last max_exchanges * 2 messages (each exchange = 1 user + 1 assistant)
        return msgs[-(self._max * 2):]

    def clear(self, chat_id: int) -> None:
        self._store.pop(chat_id, None)

    def _trim(self, chat_id: int) -> None:
        msgs = self._store.get(chat_id, [])
        max_msgs = self._max * 2 + 1  # +1 for the incoming message not yet responded
        if len(msgs) > max_msgs:
            self._store[chat_id] = msgs[-max_msgs:]


# Module-level singleton
_history = ConversationHistory(max_exchanges=settings.MAX_HISTORY_EXCHANGES)

# Anthropic client
_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY) if settings.ANTHROPIC_API_KEY else None


# ── Model tier selection ───────────────────────────────────────────────────────

_SONNET_TRIGGERS = [
    "forecast", "predict", "projection", "next year", "outlook",
    "แนวโน้ม", "พยากรณ์", "คาดการณ์", "ปีหน้า",
    "what if", "scenario", "simulate",
    "multi", "across all", "all domains", "everything",
]

_FINANCIAL_TERMS = [
    "revenue", "profit", "ebit", "margin", "cogs", "sga",
    "ar", "gl", "sales", "production", "kpi", "dso",
    "รายได้", "กำไร", "ต้นทุน", "ลูกหนี้",
]


def _pick_model(text: str, data_summary: str) -> str:
    """
    Heuristic model selection. Returns model ID.
    Sonnet triggered by: forecast keywords, 2+ year comparison,
    multi-domain data (long summary), or 3+ financial terms.
    Everything else → Haiku (much cheaper).
    """
    t_lower = text.lower()
    # Forecast keywords → Sonnet
    if any(kw in t_lower for kw in _SONNET_TRIGGERS):
        return settings.CLAUDE_SONNET_MODEL
    # 2+ years mentioned → complex comparison → Sonnet
    years = re.findall(r"\b20\d{2}\b", text)
    if len(set(years)) >= 2:
        return settings.CLAUDE_SONNET_MODEL
    # Long data summary (multi-domain) → Sonnet
    if len(data_summary) > 600:
        return settings.CLAUDE_SONNET_MODEL
    # 3+ financial terms → Sonnet
    term_count = sum(1 for t in _FINANCIAL_TERMS if t in t_lower)
    if term_count >= 3:
        return settings.CLAUDE_SONNET_MODEL
    return settings.CLAUDE_HAIKU_MODEL


# ── Main AI entry point ────────────────────────────────────────────────────────

async def answer_nl_query(
    chat_id: int,
    user_text: str,
    data_summary: str = "",
    force_model: str | None = None,
) -> str:
    """
    Answer a natural language question with optional pre-fetched data context.

    Args:
        chat_id:      Telegram chat ID (for history)
        user_text:    The user's message
        data_summary: Pre-summarised data from summariser.py (injected into prompt)
        force_model:  Override model selection (e.g. "claude-sonnet-4-6")

    Returns:
        Text response from Claude
    """
    if _client is None:
        return "AI service unavailable: ANTHROPIC_API_KEY not set."

    model = force_model or _pick_model(user_text, data_summary)
    max_tokens = settings.MAX_TOKENS_SONNET if "sonnet" in model else settings.MAX_TOKENS_HAIKU

    # Build user message with data context
    user_content = user_text
    if data_summary:
        user_content = f"{user_text}\n\n[Data context]\n{data_summary}"

    # Build messages: history + new user message
    messages = _history.get_messages(chat_id) + [
        {"role": "user", "content": user_content}
    ]

    logger.info("AI query chat_id=%d model=%s tokens_out=%d", chat_id, model, max_tokens)

    try:
        response = _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = response.content[0].text if response.content else "No response."
    except anthropic.APIError as e:
        logger.error("Anthropic API error: %s", e)
        reply = f"AI error: {str(e)[:200]}"

    # Store exchange in history
    _history.add_user(chat_id, user_text)
    _history.add_assistant(chat_id, reply)

    # Log token usage
    if hasattr(response, "usage"):
        logger.info(
            "Tokens: in=%d out=%d model=%s",
            response.usage.input_tokens, response.usage.output_tokens, model,
        )

    return reply


async def explain_variance(
    pnl_y1: dict,
    pnl_y2: dict,
    chat_id: int,
    y1: int | None = None,
    y2: int | None = None,
) -> str:
    """
    Explain P&L variance between two periods using Haiku (or Sonnet for large delta).
    Pre-summarises both P&Ls before sending to Claude.
    """
    from telegram_bot.utils.summariser import summarise_pnl

    s1 = summarise_pnl(pnl_y1)
    s2 = summarise_pnl(pnl_y2)

    # Check delta magnitude — large swings → Sonnet
    rev1 = float(pnl_y1.get("revenue", 0))
    rev2 = float(pnl_y2.get("revenue", 0))
    delta_pct = abs(rev2 - rev1) / abs(rev1) * 100 if rev1 else 100
    model = settings.CLAUDE_SONNET_MODEL if delta_pct > 30 else settings.CLAUDE_HAIKU_MODEL

    period_label = f"{y1} vs {y2}" if y1 and y2 else "period comparison"
    prompt = (
        f"Analyze this P&L variance ({period_label}):\n\n"
        f"PERIOD 1 ({y1 or 'Y1'}):\n{s1}\n\n"
        f"PERIOD 2 ({y2 or 'Y2'}):\n{s2}\n\n"
        "Explain the top 3 variance drivers in concise bullet points. "
        "Focus on what changed and what likely caused it."
    )

    return await answer_nl_query(chat_id, prompt, force_model=model)


async def generate_forecast(
    chat_id: int,
    historical_summaries: list[str],
    target_year: int | None = None,
) -> str:
    """
    Generate a financial forecast using Sonnet.
    Always uses Sonnet — forecast requires more reasoning capability.
    """
    history_text = "\n\n".join(
        f"Period {i+1}:\n{s}" for i, s in enumerate(historical_summaries)
    )
    target = f" for {target_year}" if target_year else ""
    prompt = (
        f"Based on this historical financial data:\n\n{history_text}\n\n"
        f"Provide a 2-3 sentence financial outlook{target}. "
        "Mention key risks and opportunities. Be realistic — add caveats where data is limited."
    )

    return await answer_nl_query(
        chat_id, prompt,
        data_summary=history_text,
        force_model=settings.CLAUDE_SONNET_MODEL,
    )


def clear_history(chat_id: int) -> None:
    """Clear conversation history for a user."""
    _history.clear(chat_id)
