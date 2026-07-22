from pathlib import Path

from script_catalog.scanner import RepoConfig, load_repos_config, scan_repo, scan_all


def _make_fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "fake_repo"
    (root / "cost").mkdir(parents=True)
    (root / "cost" / "run_report.py").write_text(
        'if __name__ == "__main__":\n    print("run")\n'
    )
    (root / "cost" / "helper.py").write_text("def helper():\n    return 1\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "junk.py").write_text(
        'if __name__ == "__main__":\n    pass\n'
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_something.py").write_text(
        'if __name__ == "__main__":\n    pass\n'
    )
    (root / "run.bat").write_text("@echo off\necho hi\n")
    return root


def test_scan_repo_finds_only_entrypoints_outside_excluded_dirs(tmp_path):
    root = _make_fake_repo(tmp_path)
    repo = RepoConfig(name="fake", root=root, exclude_dirs=["tests"])

    entries = scan_repo(repo)
    ids = {e["id"] for e in entries}

    assert "fake:cost/run_report.py" in ids
    assert "fake:run.bat" in ids
    assert "fake:cost/helper.py" not in ids       # not an entry-point
    assert "fake:tests/test_something.py" not in ids   # excluded dir
    assert not any("__pycache__" in e["id"] for e in entries)  # always excluded


def test_scan_repo_entry_has_expected_fields(tmp_path):
    root = _make_fake_repo(tmp_path)
    repo = RepoConfig(name="fake", root=root, exclude_dirs=["tests"])

    entries = scan_repo(repo)
    bat_entry = next(e for e in entries if e["id"] == "fake:run.bat")

    assert bat_entry["repo"] == "fake"
    assert bat_entry["language"] == "bat"
    assert bat_entry["path"] == str(root / "run.bat")
    assert bat_entry["last_modified"]  # non-empty YYYY-MM-DD string


def test_scan_repo_returns_empty_list_for_missing_root(tmp_path):
    repo = RepoConfig(name="ghost", root=tmp_path / "does_not_exist", exclude_dirs=[])
    assert scan_repo(repo) == []


def test_scan_all_combines_every_repo(tmp_path):
    root1 = _make_fake_repo(tmp_path)
    root2 = tmp_path / "fake_repo_2"
    root2.mkdir()
    (root2 / "run2.bat").write_text("@echo off\n")

    repos = [
        RepoConfig(name="fake", root=root1, exclude_dirs=["tests"]),
        RepoConfig(name="fake2", root=root2, exclude_dirs=[]),
    ]
    entries = scan_all(repos)
    ids = {e["id"] for e in entries}

    assert "fake:run.bat" in ids
    assert "fake2:run2.bat" in ids


def test_load_repos_config_parses_yaml(tmp_path):
    config_path = tmp_path / "repos.yaml"
    config_path.write_text(
        "repos:\n"
        "  - name: alpha\n"
        "    root: \"/tmp/alpha\"\n"
        "    exclude_dirs: [tests, .venv]\n"
        "  - name: beta\n"
        "    root: \"/tmp/beta\"\n"
    )

    repos = load_repos_config(config_path)

    assert len(repos) == 2
    assert repos[0].name == "alpha"
    assert repos[0].root == Path("/tmp/alpha")
    assert repos[0].exclude_dirs == ["tests", ".venv"]
    assert repos[1].exclude_dirs == []  # defaults to empty list when omitted
