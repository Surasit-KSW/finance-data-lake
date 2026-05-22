"""
core/config.py — Centralized settings using pydantic-settings
All paths resolve relative to project root (parent of backend/)

Cloud-ready: set DATABASE_URL env var to switch from DuckDB to PostgreSQL.
"""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Paths ────────────────────────────────────────────────
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

    @property
    def DUCK_DB(self) -> Path:
        return self.PROJECT_ROOT / "finance_lake.duckdb"

    @property
    def OPS_DB(self) -> Path:
        return self.PROJECT_ROOT / "operations.db"

    @property
    def SILVER(self) -> Path:
        return self.PROJECT_ROOT / "02_Silver_Cleaned"

    @property
    def GOLD(self) -> Path:
        return self.PROJECT_ROOT / "03_Gold_DataMarts"

    @property
    def BRONZE(self) -> Path:
        return self.PROJECT_ROOT / "01_Bronze_Raw"

    @property
    def PIPELINE_SCRIPT(self) -> Path:
        return self.PROJECT_ROOT / "run_pipeline.py"

    @property
    def CONFIG_DIR(self) -> Path:
        return self.PROJECT_ROOT / "08_Config"

    # ── API ──────────────────────────────────────────────────
    API_TITLE: str = "Finance Data Lake API"
    API_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"   # versioned — consumers use /api/v1/...

    # ── Cloud DB (optional) ──────────────────────────────────
    # Leave empty to use local DuckDB.
    # Set DATABASE_URL="postgresql://user:pass@host:5432/db" for cloud.
    DATABASE_URL: str = ""

    # ── API Keys ─────────────────────────────────────────────
    # Set LEADSHEET_API_KEY in .env to protect /leadsheet/build.
    # Leave empty to allow unauthenticated access (local dev).
    LEADSHEET_API_KEY: str = ""

    # ── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: list = [
        "http://localhost:3000",   # main-dashboard Next.js
        "http://localhost:3001",   # fin-dashboard Next.js
        "http://localhost:8501",   # Streamlit
        "http://localhost:8502",
        "*",                       # dev: allow all (restrict on production)
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"   # ignore unknown env vars (e.g. ANTHROPIC_API_KEY)

    @property
    def use_postgres(self) -> bool:
        return bool(self.DATABASE_URL)


settings = Settings()
