"""
telegram_bot/config.py
======================
Bot configuration via pydantic-settings.
Reads from the same .env file as backend/core/config.py (extra="ignore" avoids conflicts).
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pydantic_settings import BaseSettings


class BotSettings(BaseSettings):
    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USERS: str = ""   # comma-separated chat IDs e.g. "123456789,987654321"

    # ── Claude API ────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"
    CLAUDE_SONNET_MODEL: str = "claude-sonnet-4-6"
    MAX_HISTORY_EXCHANGES: int = 3     # sliding window per user
    MAX_TOKENS_HAIKU: int = 1024
    MAX_TOKENS_SONNET: int = 2048

    # ── Cache ─────────────────────────────────────────────────────────────────
    CACHE_TTL_SECONDS: int = 300       # 5 minutes

    # ── Google Drive (optional — disabled if blank) ───────────────────────────
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # path to service account key JSON
    GOOGLE_DRIVE_FOLDER_ID: str = ""       # folder ID from Drive URL

    # ── API ───────────────────────────────────────────────────────────────────
    DATA_LAKE_URL: str = "http://localhost:8000"
    BOT_REPORT_CHAR_LIMIT: int = 4000  # chars before auto-exporting to Drive

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"              # coexists with backend's Settings class

    @property
    def allowed_user_ids(self) -> set[int]:
        """Parse TELEGRAM_ALLOWED_USERS into a set of integer chat IDs."""
        if not self.TELEGRAM_ALLOWED_USERS.strip():
            return set()
        ids = set()
        for part in self.TELEGRAM_ALLOWED_USERS.split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                ids.add(int(part))
        return ids

    @property
    def drive_enabled(self) -> bool:
        return bool(self.GOOGLE_SERVICE_ACCOUNT_JSON and self.GOOGLE_DRIVE_FOLDER_ID)


# Module-level singleton
settings = BotSettings()
