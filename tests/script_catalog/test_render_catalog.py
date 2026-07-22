import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from render_catalog import run_render


def test_run_render_writes_markdown_file(tmp_path):
    catalog_path = tmp_path / "script-catalog.json"
    catalog_path.write_text(json.dumps([{
        "id": "demo:job.py", "repo": "demo", "path": "/x/job.py",
        "language": "py", "category": "Commission",
        "description": "Runs commission calc", "cli_flags": [],
        "status": "active", "last_modified": "2026-07-01",
        "last_scanned": "2026-07-22", "notes": None,
    }]))
    output_path = tmp_path / "script-commands.md"

    markdown = run_render(catalog_path, output_path, repo_count=7)

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == markdown
    assert "job.py" in markdown
    assert "Commission" in markdown
