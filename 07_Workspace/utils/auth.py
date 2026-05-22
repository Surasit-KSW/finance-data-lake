"""
Google OAuth Helper — Finance Workspace
Prepared by: Claude Code
"""

import json
from pathlib import Path
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from config.settings import CLIENT_SECRET_FILE, TOKEN_FILE, GOOGLE_SCOPES


def get_credentials() -> Credentials:
    """
    โหลด credentials จาก token.json (refresh อัตโนมัติ)
    ถ้ายังไม่มี token → เปิด browser ให้ login
    """
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE:
                raise FileNotFoundError(
                    "ไม่พบไฟล์ client_secret_*.json — "
                    "ดาวน์โหลดจาก Google Cloud Console แล้วใส่ไว้ในโฟลเดอร์ root"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())
        print(f"Token saved: {TOKEN_FILE}")

    return creds


def get_gspread_client() -> gspread.Client:
    """Return authenticated gspread client"""
    creds = get_credentials()
    return gspread.authorize(creds)
