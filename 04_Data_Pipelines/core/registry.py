"""
core/registry.py — Loads company_registry.yaml and resolves Bronze paths.
"""
from pathlib import Path
import yaml


class CompanyRegistry:
    """
    Loads company definitions from company_registry.yaml.
    Resolves all bronze_paths to absolute Paths using project_root.
    """

    def __init__(self, config_path: Path, project_root: Path):
        self._project_root = Path(project_root)
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self._companies = raw.get("companies", {})

    def get(self, name: str) -> dict:
        """
        Return company config dict for the given company name.
        bronze_paths values are resolved to absolute Path objects.
        Raises KeyError if company not found.
        """
        if name not in self._companies:
            raise KeyError(f"Unknown company '{name}'. Available: {list(self._companies.keys())}")
        entry = dict(self._companies[name])
        entry["bronze_paths"] = {
            domain: self._project_root / rel_path
            for domain, rel_path in entry.get("bronze_paths", {}).items()
        }
        return entry

    def all_companies(self) -> list:
        """Return list of all company names in registry."""
        return list(self._companies.keys())
