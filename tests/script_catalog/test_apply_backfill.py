import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from apply_backfill import run_apply


def test_run_apply_merges_multiple_backfill_files(tmp_path):
    catalog_path = tmp_path / "script-catalog.json"
    catalog_path.write_text(json.dumps([
        {"id": "demo:a.py", "repo": "demo", "path": "/x/a.py", "language": "py",
         "category": None, "description": None, "cli_flags": [],
         "status": "needs_description", "last_modified": "2026-07-01",
         "last_scanned": "2026-07-22", "notes": None},
        {"id": "demo:b.py", "repo": "demo", "path": "/x/b.py", "language": "py",
         "category": None, "description": None, "cli_flags": [],
         "status": "needs_description", "last_modified": "2026-07-01",
         "last_scanned": "2026-07-22", "notes": None},
    ]))

    backfill_1 = tmp_path / "backfill_demo_part1.json"
    backfill_1.write_text(json.dumps({
        "demo:a.py": {"description": "Does A", "category": "Commission"},
    }))
    backfill_2 = tmp_path / "backfill_demo_part2.json"
    backfill_2.write_text(json.dumps({
        "demo:b.py": {"description": "Does B", "category": "Reconciliation"},
    }))

    updated = run_apply(catalog_path, [backfill_1, backfill_2])

    assert all(e["status"] == "active" for e in updated)
    saved = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert saved == updated
