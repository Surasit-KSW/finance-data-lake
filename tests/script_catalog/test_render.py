from script_catalog.render import render_markdown, CATEGORY_ORDER


def _entry(**overrides):
    base = {
        "id": "repo:script.py", "repo": "repo", "path": "/x/script.py",
        "language": "py", "category": "Month-End Close",
        "description": "Does a thing", "cli_flags": [],
        "status": "active", "last_modified": "2026-07-01",
        "last_scanned": "2026-07-22", "notes": None,
    }
    base.update(overrides)
    return base


def test_render_groups_by_category_in_fixed_order():
    catalog = [
        _entry(id="repo:b.py", path="/x/b.py", category="Commission"),
        _entry(id="repo:a.py", path="/x/a.py", category="Month-End Close"),
    ]
    md = render_markdown(catalog, repo_count=7)

    month_end_pos = md.index("## Month-End Close")
    commission_pos = md.index("## Commission")
    assert month_end_pos < commission_pos  # Month-End Close comes first in CATEGORY_ORDER


def test_render_excludes_stale_entries():
    catalog = [_entry(status="stale", path="/x/gone.py")]
    md = render_markdown(catalog, repo_count=7)
    assert "gone.py" not in md


def test_render_includes_command_and_description():
    catalog = [_entry(
        path="/x/mb51_cost_breakdown.py",
        cli_flags=["--dry-run"],
        description="MB51 cost breakdown",
    )]
    md = render_markdown(catalog, repo_count=7)
    assert "mb51_cost_breakdown.py" in md
    assert "--dry-run" in md
    assert "MB51 cost breakdown" in md


def test_render_puts_uncategorized_entries_in_own_section():
    catalog = [_entry(category=None, status="needs_description")]
    md = render_markdown(catalog, repo_count=7)
    assert "Uncategorized" in md


def test_render_header_shows_repo_and_script_count():
    catalog = [_entry()]
    md = render_markdown(catalog, repo_count=7)
    assert "7 repos scanned" in md
    assert "1 scripts" in md


def test_category_order_has_exactly_ten_fixed_categories():
    assert len(CATEGORY_ORDER) == 10
    assert CATEGORY_ORDER[0] == "Month-End Close"
    assert "Shared Utilities" in CATEGORY_ORDER
