from script_catalog.merge import merge_catalog


def test_new_entry_is_added_with_needs_description_status():
    existing = []
    scanned = [{
        "id": "repo:new.py", "repo": "repo", "path": "/x/new.py",
        "language": "py", "last_modified": "2026-07-01",
        "description": None, "cli_flags": [],
    }]

    merged = merge_catalog(existing, scanned)

    assert len(merged) == 1
    assert merged[0]["status"] == "needs_description"
    assert merged[0]["category"] is None


def test_existing_entry_preserves_ai_backfilled_fields():
    existing = [{
        "id": "repo:gl_close.py", "repo": "repo", "path": "/old/path.py",
        "language": "py", "category": "Month-End Close",
        "description": "GL close analytics", "cli_flags": [],
        "status": "active", "last_modified": "2026-06-01",
        "last_scanned": "2026-06-01", "notes": "known issue: X",
    }]
    scanned = [{
        "id": "repo:gl_close.py", "repo": "repo", "path": "/new/path.py",
        "language": "py", "last_modified": "2026-07-20",
        "description": None, "cli_flags": ["--month", "--deep"],
    }]

    merged = merge_catalog(existing, scanned)

    assert len(merged) == 1
    entry = merged[0]
    assert entry["category"] == "Month-End Close"       # preserved
    assert entry["description"] == "GL close analytics"  # preserved
    assert entry["notes"] == "known issue: X"             # preserved
    assert entry["path"] == "/new/path.py"                # refreshed
    assert entry["cli_flags"] == ["--month", "--deep"]    # refreshed
    assert entry["last_modified"] == "2026-07-20"         # refreshed
    assert entry["status"] == "active"


def test_missing_entry_is_marked_stale_not_deleted():
    existing = [{
        "id": "repo:removed.py", "repo": "repo", "path": "/x/removed.py",
        "language": "py", "category": "Commission",
        "description": "old script", "cli_flags": [],
        "status": "active", "last_modified": "2026-05-01",
        "last_scanned": "2026-05-01", "notes": None,
    }]
    scanned = []

    merged = merge_catalog(existing, scanned)

    assert len(merged) == 1
    assert merged[0]["status"] == "stale"
    assert merged[0]["description"] == "old script"  # untouched


def test_previously_stale_entry_reactivates_when_seen_again():
    existing = [{
        "id": "repo:back.py", "repo": "repo", "path": "/x/back.py",
        "language": "py", "category": "Commission",
        "description": "back again", "cli_flags": [],
        "status": "stale", "last_modified": "2026-05-01",
        "last_scanned": "2026-06-01", "notes": None,
    }]
    scanned = [{
        "id": "repo:back.py", "repo": "repo", "path": "/x/back.py",
        "language": "py", "last_modified": "2026-07-22",
        "description": None, "cli_flags": [],
    }]

    merged = merge_catalog(existing, scanned)

    assert merged[0]["status"] == "active"
    assert merged[0]["description"] == "back again"
