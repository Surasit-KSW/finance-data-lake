"""
drive_organizer.py
==================
จัดโครงสร้าง Google Drive สำหรับ Month-End Close

Folder layout:
  Month-End Close/
  ├── MM.YYYY/          ← ไฟล์รวม AMC+GA+STC ต่อเดือน
  │   └── monthend_close_MMYYYY  (Google Sheet)
  ├── AMC/              ← สำหรับไฟล์ AMC อื่นๆ (SAP export, recon ฯลฯ)
  ├── GA/
  └── STC/

Usage:
  from utils.drive_organizer import DriveOrganizer
  org = DriveOrganizer(creds)
  sheet_id = org.upload_and_organize(local_xlsx_path, month="05", year="2026")
"""

import io
import sys
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


# Root folder name ใน My Drive
MONTHEND_ROOT_NAME = "Month-End Close"
COMPANY_FOLDERS    = ["AMC", "GA", "STC"]


class DriveOrganizer:
    def __init__(self, creds):
        self.service = build("drive", "v3", credentials=creds)

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    def _find_folder(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """หา folder ID ตามชื่อ (ใน parent ถ้าระบุ) — คืน None ถ้าไม่เจอ"""
        q = (
            f"name='{name}' "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        if parent_id:
            q += f" and '{parent_id}' in parents"

        res = self.service.files().list(
            q=q, spaces="drive", fields="files(id,name)"
        ).execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def _create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """สร้าง folder แล้วคืน folder ID"""
        meta = {
            "name":     name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            meta["parents"] = [parent_id]
        f = self.service.files().create(body=meta, fields="id").execute()
        return f["id"]

    def _get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> tuple[str, bool]:
        """คืน (folder_id, created: bool)"""
        fid = self._find_folder(name, parent_id)
        if fid:
            return fid, False
        fid = self._create_folder(name, parent_id)
        return fid, True

    def _list_files_in_folder(self, folder_id: str) -> list[dict]:
        """List ไฟล์ใน folder (ไม่รวม folder)"""
        res = self.service.files().list(
            q=(
                f"'{folder_id}' in parents "
                f"and mimeType!='application/vnd.google-apps.folder' "
                f"and trashed=false"
            ),
            spaces="drive",
            fields="files(id,name,modifiedTime,mimeType)"
        ).execute()
        return res.get("files", [])

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def ensure_structure(self) -> dict:
        """
        สร้าง/ตรวจสอบ folder structure ทั้งหมด
        คืน dict ของ folder IDs
        """
        folders = {}

        # Root: Month-End Close
        root_id, created = self._get_or_create_folder(MONTHEND_ROOT_NAME)
        folders["root"] = root_id
        if created:
            print(f"  [Drive] Created root folder: '{MONTHEND_ROOT_NAME}'")
        else:
            print(f"  [Drive] Found root folder: '{MONTHEND_ROOT_NAME}'")

        # Company folders: AMC / GA / STC
        for co in COMPANY_FOLDERS:
            fid, created = self._get_or_create_folder(co, root_id)
            folders[co] = fid
            status = "Created" if created else "Found"
            print(f"  [Drive] {status} folder: '{MONTHEND_ROOT_NAME}/{co}'")

        return folders

    def get_or_create_period_folder(self, month: str, year: str, root_id: str) -> tuple[str, bool]:
        """สร้าง/หา period subfolder เช่น '05.2026'"""
        period_name = f"{month}.{year}"
        fid, created = self._get_or_create_folder(period_name, root_id)
        return fid, created

    def check_existing_files(self, period_folder_id: str, period_label: str) -> list[dict]:
        """ตรวจสอบว่ามีไฟล์เก่าอยู่แล้วไหม แล้วถามผู้ใช้"""
        existing = self._list_files_in_folder(period_folder_id)
        if not existing:
            return []

        print(f"\n  [Drive] พบไฟล์เก่าใน folder '{period_label}':")
        for f in existing:
            print(f"    - {f['name']}  (modified: {f['modifiedTime'][:10]})")
        return existing

    def ask_archive_old_files(self, existing_files: list[dict],
                               period_folder_id: str,
                               root_id: str,
                               period_label: str) -> bool:
        """
        ถามผู้ใช้ว่าจะ archive ไฟล์เก่าหรือไม่
        ถ้า archive → ย้ายไป 'Month-End Close/_Archive/MM.YYYY'
        คืน True ถ้า user ยืนยันจะ proceed
        """
        print()
        answer = input(
            f"  มีไฟล์เก่า {len(existing_files)} ไฟล์ใน '{period_label}'\n"
            f"  จะทำอะไร? [a=archive / k=keep ทั้งคู่ / s=skip ไม่ gen ใหม่]: "
        ).strip().lower()

        if answer == "s":
            print("  [Drive] Skip — ไม่สร้างไฟล์ใหม่")
            return False

        if answer == "a":
            # สร้าง _Archive/MM.YYYY folder
            archive_root_id, _ = self._get_or_create_folder("_Archive", root_id)
            archive_period_id, _ = self._get_or_create_folder(period_label, archive_root_id)
            for f in existing_files:
                self.service.files().update(
                    fileId=f["id"],
                    addParents=str(archive_period_id),
                    removeParents=str(period_folder_id),
                    fields="id,parents"
                ).execute()
                print(f"  [Drive] Archived: {f['name']}")

        return True  # proceed with new file (keep หรือหลัง archive)

    def upload_xlsx_as_sheet(self, local_path: Path, sheet_name: str,
                              parent_folder_id: str) -> str:
        """
        Upload .xlsx file → แปลงเป็น Google Sheet
        คืน spreadsheet ID
        """
        with open(local_path, "rb") as f:
            content = f.read()

        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            resumable=False
        )
        meta = {
            "name":     sheet_name,
            "mimeType": "application/vnd.google-apps.spreadsheet",  # auto-convert
            "parents":  [parent_folder_id],
        }
        result = self.service.files().create(
            body=meta, media_body=media, fields="id,name,webViewLink"
        ).execute()

        print(f"  [Drive] Uploaded: '{result['name']}'")
        print(f"  [Drive] URL: {result['webViewLink']}")
        return result["id"]

    # ─────────────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────────────

    def upload_and_organize(self, local_xlsx: Path, month: str, year: str) -> Optional[str]:
        """
        Full workflow:
        1. Ensure folder structure
        2. Get/create period subfolder
        3. Check old files → ask user
        4. Upload Excel → Google Sheet
        คืน spreadsheet ID หรือ None ถ้า skip
        """
        period_label = f"{month}.{year}"
        sheet_name   = f"monthend_close_{month}{year}"

        print(f"\n[Drive Organizer] period: {period_label}")

        # 1. Folder structure
        folders   = self.ensure_structure()
        root_id   = folders["root"]

        # 2. Period folder
        period_id, created = self.get_or_create_period_folder(month, year, root_id)
        if created:
            print(f"  [Drive] Created period folder: '{period_label}'")
        else:
            print(f"  [Drive] Found period folder: '{period_label}'")

        # 3. Check old files
        existing = self.check_existing_files(period_id, period_label)
        if existing:
            proceed = self.ask_archive_old_files(existing, period_id, root_id, period_label)
            if not proceed:
                return None

        # 4. Upload
        sheet_id = self.upload_xlsx_as_sheet(local_xlsx, sheet_name, period_id)
        return sheet_id
