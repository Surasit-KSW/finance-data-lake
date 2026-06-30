from pathlib import Path
import pytest
from core.utils import to_posix, get_year_suffix, detect_year_dirs


def test_to_posix_converts_backslashes():
    result = to_posix(Path("C:\\foo\\bar\\file.parquet"))
    assert "\\" not in result
    assert result == "C:/foo/bar/file.parquet"


def test_to_posix_leaves_forward_slashes():
    result = to_posix("C:/foo/bar")
    assert result == "C:/foo/bar"


def test_get_year_suffix_two_years():
    assert get_year_suffix([2024, 2025, 2026]) == "24_26"


def test_get_year_suffix_single_year():
    assert get_year_suffix([2025]) == "25_25"


def test_detect_year_dirs(tmp_path):
    (tmp_path / "2024").mkdir()
    (tmp_path / "2025").mkdir()
    (tmp_path / "not_a_year").mkdir()
    (tmp_path / "123").mkdir()   # too short
    result = detect_year_dirs(tmp_path)
    assert result == [2024, 2025]


def test_detect_year_dirs_empty(tmp_path):
    assert detect_year_dirs(tmp_path) == []
