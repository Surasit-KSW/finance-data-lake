"""
script_catalog/merge.py
=========================
Merge freshly scanned entries into the existing catalog without clobbering
AI-backfilled `description` / `category` / `notes` fields.
"""
import datetime


def merge_catalog(existing: list[dict], scanned: list[dict]) -> list[dict]:
    """
    Combine `existing` catalog entries with freshly `scanned` ones.

    - New id -> added with status "needs_description", category None.
    - Existing id still present in scan -> mechanical fields refreshed
      (path, language, last_modified, cli_flags, last_scanned);
      description/category/notes preserved; stale entries reactivate.
    - Existing id missing from scan -> kept but marked status "stale"
      (never deleted).
    """
    existing_by_id = {entry["id"]: entry for entry in existing}
    scanned_by_id = {entry["id"]: entry for entry in scanned}
    today = datetime.date.today().isoformat()

    merged: list[dict] = []

    for scan_id, scanned_entry in scanned_by_id.items():
        if scan_id in existing_by_id:
            merged_entry = dict(existing_by_id[scan_id])
            merged_entry["path"] = scanned_entry["path"]
            merged_entry["language"] = scanned_entry["language"]
            merged_entry["last_modified"] = scanned_entry["last_modified"]
            merged_entry["cli_flags"] = scanned_entry.get("cli_flags", [])
            merged_entry["last_scanned"] = today
            if merged_entry.get("status") == "stale":
                merged_entry["status"] = "active"
            merged.append(merged_entry)
        else:
            new_entry = dict(scanned_entry)
            new_entry["category"] = None
            new_entry["notes"] = None
            new_entry["status"] = "needs_description"
            new_entry["last_scanned"] = today
            merged.append(new_entry)

    for existing_id, existing_entry in existing_by_id.items():
        if existing_id not in scanned_by_id:
            stale_entry = dict(existing_entry)
            stale_entry["status"] = "stale"
            stale_entry["last_scanned"] = today
            merged.append(stale_entry)

    return merged
