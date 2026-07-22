import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from scan_scripts import run_scan


def test_run_scan_writes_new_catalog_from_scratch(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "job.py").write_text(
        '"""\njob.py — Do the job.\n"""\n'
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--month')\n"
        'if __name__ == "__main__":\n    pass\n',
        encoding="utf-8",
    )

    config_path = tmp_path / "repos.yaml"
    config_path.write_text(
        f"repos:\n  - name: demo\n    root: \"{repo_root.as_posix()}\"\n"
    )
    catalog_path = tmp_path / "script-catalog.json"

    result = run_scan(config_path, catalog_path)

    assert len(result) == 1
    assert result[0]["id"] == "demo:job.py"
    assert result[0]["status"] == "needs_description"
    assert result[0]["description"] == "job.py — Do the job."
    assert result[0]["cli_flags"] == ["--month"]

    saved = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert saved == result


def test_run_scan_preserves_backfilled_fields_on_rescan(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "job.py").write_text('if __name__ == "__main__":\n    pass\n')

    config_path = tmp_path / "repos.yaml"
    config_path.write_text(
        f"repos:\n  - name: demo\n    root: \"{repo_root.as_posix()}\"\n"
    )
    catalog_path = tmp_path / "script-catalog.json"
    catalog_path.write_text(json.dumps([{
        "id": "demo:job.py", "repo": "demo", "path": str(repo_root / "job.py"),
        "language": "py", "category": "Commission",
        "description": "Backfilled description", "cli_flags": [],
        "status": "active", "last_modified": "2026-01-01",
        "last_scanned": "2026-01-01", "notes": None,
    }]))

    result = run_scan(config_path, catalog_path)

    assert result[0]["category"] == "Commission"
    assert result[0]["description"] == "Backfilled description"
