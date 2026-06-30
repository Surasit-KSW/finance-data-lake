"""
core/utils.py — Shared path and naming utilities for ETL pipeline
"""
from pathlib import Path


def to_posix(path) -> str:
    """Convert Windows path to forward slashes (required by DuckDB SQL)"""
    return str(path).replace("\\", "/")


def get_year_suffix(years: list) -> str:
    """
    Convert a list of years to a two-digit range suffix.
    [2024, 2025, 2026] → '24_26'
    [2025] → '25_25'
    """
    years = sorted(int(y) for y in years)
    return f"{str(years[0])[2:]}_{str(years[-1])[2:]}"


def detect_year_dirs(base_path: Path) -> list:
    """
    Return sorted list of 4-digit year subdirectory names under base_path.
    Ignores non-directories and non-4-digit names.
    """
    if not base_path.exists():
        return []
    return sorted([
        int(d.name)
        for d in base_path.iterdir()
        if d.is_dir() and d.name.isdigit() and len(d.name) == 4
    ])
