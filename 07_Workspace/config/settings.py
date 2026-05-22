"""
Finance Workspace Settings — migrated to _Finance_Data_Lake/07_Workspace
Prepared by: Claude Code
"""

import os
from pathlib import Path

# ===== Project Roots =====
WORKSPACE_DIR = Path(__file__).parent.parent          # 07_Workspace/
DATA_LAKE_DIR = WORKSPACE_DIR.parent                  # _Finance_Data_Lake/
BASE_DIR = WORKSPACE_DIR                              # backward compat alias

# ===== Google OAuth =====
CREDENTIALS_DIR = WORKSPACE_DIR / ".credentials"
CLIENT_SECRET_FILE = next(DATA_LAKE_DIR.glob("client_secret_*.json"), None)
TOKEN_FILE = CREDENTIALS_DIR / "token.json"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ===== Google Drive Folder IDs =====
DRIVE_FOLDERS = {
    "root":       os.getenv("DRIVE_ROOT_ID", ""),
    "templates":  os.getenv("DRIVE_TEMPLATES_ID", ""),
    "raw":        os.getenv("DRIVE_RAW_ID", ""),
    "working":    os.getenv("DRIVE_WORKING_ID", ""),
    "review":     os.getenv("DRIVE_REVIEW_ID", ""),
    "final":      os.getenv("DRIVE_FINAL_ID", ""),
}

# ===== Log Sheet IDs =====
RECON_LOG_SHEET_ID     = os.getenv("RECON_LOG_SHEET_ID", "")
ANALYTICS_LOG_SHEET_ID = os.getenv("ANALYTICS_LOG_SHEET_ID", "")

# ===== Finance Constants =====
CURRENCY = "THB"
DECIMAL_PLACES = 2
RECONCILE_TOLERANCE = 0.01       # ±0.01 บาท
DATE_FORMAT = "%d/%m/%Y"
NUMBER_FORMAT = "#,##0.00"
SUMMARY_LANGUAGE = "th"

# ===== Outlier Threshold =====
OUTLIER_STD_MULTIPLIER   = 2           # mean ± 2 std dev
OUTLIER_FORCE_FLAG_AMOUNT = 500_000    # บาท — flag ทุกรายการเกินนี้

# ===== Reconciliation Thresholds =====
MATCH_RATE_WARNING     = 0.80       # แจ้งเตือนถ้า match rate < 80%
LARGE_UNMATCHED_AMOUNT = 1_000_000  # บาท — หยุดและถามถ้าไม่ match

# ===== Forecast Settings =====
FORECAST_DEFAULT_HORIZON   = 3      # เดือน
FORECAST_CONFIDENCE_LEVEL  = 0.90
FORECAST_MIN_MONTHS_MA     = 6      # ต้องมีข้อมูลอย่างน้อย 6 เดือน
FORECAST_MIN_MONTHS_LINEAR = 24     # ใช้ Linear Trend เมื่อมี >= 24 เดือน

# ===== Match Keys (default) =====
DEFAULT_MATCH_KEYS = {
    "AP_vs_Bank": {
        "key": ["invoice_number", "amount"],
        "date_tolerance_days": 3,
    },
    "AR_vs_Receipt": {
        "key": ["receipt_number", "amount"],
        "date_tolerance_days": 0,
    },
    "Intercompany": {
        "key": ["ref_number", "entity_code", "amount"],
        "date_tolerance_days": 0,
    },
}

# ===== Data Paths =====
PRD_GI_DIR = DATA_LAKE_DIR / "01_Bronze_Raw" / "PRD_GI"
MASTER_DIR  = DATA_LAKE_DIR / "01_Bronze_Raw" / "Master"
WORKING_DIR = WORKSPACE_DIR / "02_Working"
