from pathlib import Path

from script_catalog.extract import extract_description, extract_cli_flags


def test_extract_description_returns_first_docstring_line(tmp_path):
    f = tmp_path / "report.py"
    f.write_text(
        '"""\n'
        "report.py — Generate the monthly report.\n"
        "\n"
        "Extra detail line.\n"
        '"""\n'
        "print('hi')\n",
        encoding="utf-8",
    )
    assert extract_description(f) == "report.py — Generate the monthly report."


def test_extract_description_returns_none_when_no_docstring(tmp_path):
    f = tmp_path / "no_doc.py"
    f.write_text("print('hi')\n")
    assert extract_description(f) is None


def test_extract_description_returns_none_for_non_python_file(tmp_path):
    f = tmp_path / "run.bat"
    f.write_text("@echo off\n")
    assert extract_description(f) is None


def test_extract_description_returns_none_on_syntax_error(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def broken(:\n")
    assert extract_description(f) is None


def test_extract_cli_flags_finds_add_argument_flags(tmp_path):
    f = tmp_path / "cli.py"
    f.write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--month', type=int)\n"
        "parser.add_argument('--dry-run', action='store_true')\n"
        "parser.add_argument('positional')\n"
    )
    flags = extract_cli_flags(f)
    assert flags == ["--month", "--dry-run"]


def test_extract_cli_flags_returns_empty_list_when_no_argparse(tmp_path):
    f = tmp_path / "plain.py"
    f.write_text("print('hi')\n")
    assert extract_cli_flags(f) == []


def test_extract_cli_flags_returns_empty_list_for_non_python_file(tmp_path):
    f = tmp_path / "run.bat"
    f.write_text("@echo off\n")
    assert extract_cli_flags(f) == []
