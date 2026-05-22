"""
Google Sheets Helper — Finance Workspace
Prepared by: Claude Code
"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Any

import gspread
from gspread import Spreadsheet, Worksheet

from config.settings import (
    DRIVE_FOLDERS,
    DATE_FORMAT,
    DECIMAL_PLACES,
)

PREPARED_BY = "Claude Code"


# ───────────────────────────── Formatting ──────────────────────────────

def fmt_number(value: float | None) -> str:
    """Format เป็น #,##0.00"""
    if value is None:
        return ""
    return f"{round(value, DECIMAL_PLACES):,.2f}"


def fmt_date(dt: datetime | None) -> str:
    """Format วันที่เป็น DD/MM/YYYY"""
    if dt is None:
        return ""
    return dt.strftime(DATE_FORMAT)


def round_amount(value: float) -> float:
    """ปัดทศนิยม 2 ตำแหน่งเสมอ"""
    return round(value, DECIMAL_PLACES)


# ───────────────────────────── Sheet Operations ────────────────────────

def open_or_create_sheet(
    gc: gspread.Client,
    name: str,
    folder_id: str | None = None,
) -> Spreadsheet:
    """
    เปิด Sheet ที่มีอยู่ หรือสร้างใหม่ใน folder ที่ระบุ
    ถ้า folder_id=None → ใช้ 02_Working/
    """
    target_folder = folder_id or DRIVE_FOLDERS.get("working", "")

    try:
        return gc.open(name)
    except gspread.SpreadsheetNotFound:
        sh = gc.create(name)
        if target_folder:
            # Move to correct Drive folder
            gc.auth.authorized_session.post(
                f"https://www.googleapis.com/drive/v3/files/{sh.id}",
                params={"addParents": target_folder, "removeParents": "root"},
                json={},
            )
        print(f"Created new Sheet: {name}")
        return sh


def get_or_add_worksheet(sh: Spreadsheet, title: str) -> Worksheet:
    """Return tab ที่มีอยู่ หรือสร้าง tab ใหม่"""
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=1000, cols=26)


def clear_and_write(ws: Worksheet, headers: list[str], rows: list[list]) -> None:
    """Clear worksheet แล้วเขียน header + rows ใหม่"""
    ws.clear()
    if headers:
        ws.append_row(headers)
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")


def write_summary_tab(
    ws: Worksheet,
    title: str,
    stats: dict[str, Any],
    narrative: str = "",
) -> None:
    """
    เขียน Summary tab มาตรฐาน พร้อม timestamp และ sign-off
    """
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    rows = [
        [title],
        [],
        ["Prepared by:", PREPARED_BY],
        ["Timestamp:", timestamp],
        ["Status:", "Draft — Pending Review"],
        [],
        ["=== สรุปผล ==="],
    ]
    for key, val in stats.items():
        rows.append([key, val])

    if narrative:
        rows.append([])
        rows.append(["=== Narrative ==="])
        rows.append([narrative])

    ws.clear()
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# ───────────────────────────── Reconciliation Sheet ────────────────────

RECON_TABS = [
    "Source_A",
    "Source_B",
    "Matched",
    "Unmatched_A",
    "Unmatched_B",
    "Diff",
    "Summary",
]


def setup_recon_sheet(sh: Spreadsheet) -> dict[str, Worksheet]:
    """สร้าง tab มาตรฐานสำหรับ Reconciliation Sheet"""
    # ลบ tab เริ่มต้น "Sheet1" ถ้ายังมีอยู่
    try:
        default = sh.worksheet("Sheet1")
        if len(sh.worksheets()) > 1:
            sh.del_worksheet(default)
    except gspread.WorksheetNotFound:
        pass

    tabs = {}
    for title in RECON_TABS:
        tabs[title] = get_or_add_worksheet(sh, title)
    return tabs


# ───────────────────────────── Log Sheet ───────────────────────────────

RECON_LOG_HEADERS = [
    "Date", "Source_A", "Source_B", "Output_File",
    "Total_A", "Total_B", "Matched", "Unmatched", "Diff",
    "Match_Rate", "Status", "Reviewed_By",
]

ANALYTICS_LOG_HEADERS = [
    "Date", "Type", "Name", "Source", "Period",
    "Output_File", "Status", "Reviewed_By",
]


def append_recon_log(ws: Worksheet, entry: dict) -> None:
    """เพิ่ม row ใน reconciliation_log"""
    row = [
        entry.get("date", fmt_date(datetime.now())),
        entry.get("source_a", ""),
        entry.get("source_b", ""),
        entry.get("output_file", ""),
        entry.get("total_a", 0),
        entry.get("total_b", 0),
        entry.get("matched", 0),
        entry.get("unmatched", 0),
        entry.get("diff", 0),
        entry.get("match_rate", ""),
        entry.get("status", "Draft"),
        entry.get("reviewed_by", ""),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")


def append_analytics_log(ws: Worksheet, entry: dict) -> None:
    """เพิ่ม row ใน analytics_log"""
    row = [
        entry.get("date", fmt_date(datetime.now())),
        entry.get("type", ""),
        entry.get("name", ""),
        entry.get("source", ""),
        entry.get("period", ""),
        entry.get("output_file", ""),
        entry.get("status", "Draft"),
        entry.get("reviewed_by", ""),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
