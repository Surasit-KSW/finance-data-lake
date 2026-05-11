"""
telegram_bot/services/drive_service.py
========================================
Google Drive integration — upload DataFrames to Sheets and text to Docs.
Only instantiated if GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_DRIVE_FOLDER_ID are set.
All Google API calls are sync; wrapped in asyncio executor for the async bot.

Setup:
  1. Create a Google Cloud project
  2. Enable Google Sheets API + Google Docs API + Google Drive API
  3. Create a service account, download JSON key
  4. Share the target Drive folder with the service account email
  5. Set GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_DRIVE_FOLDER_ID in .env
"""
import sys
import logging
import asyncio
from datetime import datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from telegram_bot.config import settings

logger = logging.getLogger(__name__)


class DriveServiceError(Exception):
    pass


class DriveService:
    """
    Google Drive integration.
    Conditionally instantiated — returns None from create() if not configured.
    """

    def __init__(self):
        self._folder_id = settings.GOOGLE_DRIVE_FOLDER_ID
        self._creds_path = settings.GOOGLE_SERVICE_ACCOUNT_JSON
        self._sheets_service = None
        self._docs_service = None
        self._drive_service = None
        self._initialized = False

    def _init_services(self) -> None:
        """Lazy-init Google API clients on first use."""
        if self._initialized:
            return
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            SCOPES = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/documents",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = service_account.Credentials.from_service_account_file(
                self._creds_path, scopes=SCOPES
            )
            self._sheets_service = build("sheets", "v4", credentials=creds)
            self._docs_service   = build("docs", "v1", credentials=creds)
            self._drive_service  = build("drive", "v3", credentials=creds)
            self._initialized = True
            logger.info("Google Drive service initialized.")
        except Exception as e:
            raise DriveServiceError(f"Google API init failed: {e}")

    def _timestamp_title(self, title: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        return f"AMC_{title}_{ts}"

    # ── Sync methods (wrapped in executor by async callers) ─────────────────

    def _create_sheet(self, df: pd.DataFrame, title: str) -> str:
        """Create a Google Sheet from a DataFrame. Returns web URL."""
        self._init_services()
        full_title = self._timestamp_title(title)

        # Create spreadsheet
        spreadsheet = self._sheets_service.spreadsheets().create(
            body={"properties": {"title": full_title}},
            fields="spreadsheetId,spreadsheetUrl",
        ).execute()
        sheet_id = spreadsheet["spreadsheetId"]
        url = spreadsheet["spreadsheetUrl"]

        # Write header + data
        values = [df.columns.tolist()] + df.fillna("").values.tolist()
        # Convert all values to strings for Sheets API
        values = [[str(cell) for cell in row] for row in values]

        self._sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

        # Move to target folder
        self._drive_service.files().update(
            fileId=sheet_id,
            addParents=self._folder_id,
            removeParents="root",
            fields="id,parents",
        ).execute()

        logger.info("Created Google Sheet: %s (%s)", full_title, url)
        return url

    def _create_doc(self, content: str, title: str) -> str:
        """Create a Google Doc from text content. Returns web URL."""
        self._init_services()
        full_title = self._timestamp_title(title)

        doc = self._docs_service.documents().create(
            body={"title": full_title}
        ).execute()
        doc_id = doc["documentId"]
        url = f"https://docs.google.com/document/d/{doc_id}/edit"

        # Insert content
        self._docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

        # Move to target folder
        self._drive_service.files().update(
            fileId=doc_id,
            addParents=self._folder_id,
            removeParents="root",
            fields="id,parents",
        ).execute()

        logger.info("Created Google Doc: %s (%s)", full_title, url)
        return url

    def _create_pnl_sheet(self, pnl: dict, title: str, year: int | None = None) -> str:
        """Create a structured P&L Google Sheet with summary rows."""
        rows = [
            ["Metric", "Amount (THB)", "Notes"],
            ["Revenue", pnl.get("revenue", 0), ""],
            ["COGS", pnl.get("cogs", 0), ""],
            ["Gross Profit", pnl.get("gross_profit", 0), f"Margin: {pnl.get('gross_margin_pct', 0):.1f}%"],
            ["SG&A", pnl.get("sga", 0), ""],
            ["EBIT", pnl.get("ebit", 0), f"Margin: {pnl.get('ebit_margin_pct', 0):.1f}%"],
            ["Finance Cost", pnl.get("finance_cost", 0), ""],
            ["EBT", pnl.get("ebt", 0), ""],
            ["Tax", pnl.get("tax", 0), ""],
            ["Net Income", pnl.get("net_income", 0), f"Margin: {pnl.get('net_margin_pct', 0):.1f}%"],
        ]
        df = pd.DataFrame(rows[1:], columns=rows[0])
        return self._create_sheet(df, title)

    # ── Async public API ────────────────────────────────────────────────────

    async def upload_dataframe(self, df: pd.DataFrame, title: str) -> str:
        """Upload DataFrame to Google Sheets. Returns URL."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._create_sheet, df, title)

    async def upload_text(self, content: str, title: str) -> str:
        """Upload text to Google Docs. Returns URL."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._create_doc, content, title)

    async def upload_pnl(self, pnl: dict, title: str, year: int | None = None) -> str:
        """Upload P&L as structured Google Sheet. Returns URL."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._create_pnl_sheet, pnl, title, year)

    @classmethod
    def create(cls) -> "DriveService | None":
        """Return DriveService instance if configured, else None."""
        if settings.drive_enabled:
            return cls()
        return None


# Module-level singleton (None if Drive not configured)
drive = DriveService.create()
