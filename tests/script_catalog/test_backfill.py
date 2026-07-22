from script_catalog.backfill import apply_backfill


def test_apply_backfill_sets_description_category_and_status():
    catalog = [{
        "id": "demo:job.py", "repo": "demo", "path": "/x/job.py",
        "language": "py", "category": None, "description": None,
        "cli_flags": [], "status": "needs_description",
        "last_modified": "2026-07-01", "last_scanned": "2026-07-22", "notes": None,
    }]
    backfill = {
        "demo:job.py": {"description": "Runs the monthly job", "category": "Commission"},
    }

    updated = apply_backfill(catalog, backfill)

    assert updated[0]["description"] == "Runs the monthly job"
    assert updated[0]["category"] == "Commission"
    assert updated[0]["status"] == "active"


def test_apply_backfill_leaves_unmatched_entries_untouched():
    catalog = [{
        "id": "demo:other.py", "repo": "demo", "path": "/x/other.py",
        "language": "py", "category": None, "description": None,
        "cli_flags": [], "status": "needs_description",
        "last_modified": "2026-07-01", "last_scanned": "2026-07-22", "notes": None,
    }]
    backfill = {"demo:job.py": {"description": "x", "category": "Commission"}}

    updated = apply_backfill(catalog, backfill)

    assert updated[0]["status"] == "needs_description"
    assert updated[0]["description"] is None
