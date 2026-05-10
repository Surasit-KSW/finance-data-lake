"""
lake_config.py
==============
Finance Data Lake — Shared Configuration Loader

Reads 08_Config/data_paths.yaml and exposes typed Path objects.
Import this in any Python script that needs data lake paths or API URL.

Usage:
    from scripts.utils.lake_config import cfg

    # Path access
    df = pd.read_parquet(cfg.silver.gl)
    template = cfg.bronze.files["leadsheet_q126"]

    # API access
    print(cfg.api.url)          # http://localhost:8000
    print(cfg.api.prefix)       # /api/v1
    print(cfg.api.tb("2026-03-31"))  # /api/v1/financial/tb/2026-03-31
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import yaml


# ---------------------------------------------------------------------------
# Locate the config file
# ---------------------------------------------------------------------------
def _find_config() -> Path:
    """Walk up from this file to find 08_Config/data_paths.yaml."""
    here = Path(__file__).resolve()
    # Try: utils/ -> 06_Scripts/ -> root
    for parent in [here.parent.parent.parent, here.parent.parent]:
        candidate = parent / "08_Config" / "data_paths.yaml"
        if candidate.exists():
            return candidate

    # Fallback: environment variable
    env_root = os.environ.get("DATA_LAKE_ROOT")
    if env_root:
        candidate = Path(env_root) / "08_Config" / "data_paths.yaml"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Cannot find 08_Config/data_paths.yaml. "
        "Set DATA_LAKE_ROOT env var or run from within the Data Lake project."
    )


# ---------------------------------------------------------------------------
# Typed config sections
# ---------------------------------------------------------------------------
@dataclass
class BronzeConfig:
    root: Path
    templates: Path
    gl: Path
    ar: Path
    ap: Path
    sales: Path
    production: Path
    fixed_assets: Path
    inventory: Path
    deposit: Path
    files: dict  # key -> Path

    def file(self, name: str) -> Path:
        """Get a specific Bronze file by name."""
        p = self.files.get(name)
        if p is None:
            raise KeyError(f"Bronze file '{name}' not in data_paths.yaml")
        return p


@dataclass
class SilverConfig:
    root: Path
    gl: Path
    ar: Path
    _sales_pattern: str      # contains {year}
    _production_pattern: str

    def sales(self, year: int) -> Path:
        return Path(self._sales_pattern.format(year=year))

    def production(self, year: int) -> Path:
        return Path(self._production_pattern.format(year=year))


@dataclass
class GoldConfig:
    root: Path
    gl_summary: Path


@dataclass
class ApiConfig:
    url: str        # http://localhost:8000
    version: str    # v1
    prefix: str     # /api/v1
    docs: str

    def endpoint(self, path: str) -> str:
        """Build full endpoint URL."""
        return f"{self.url}{self.prefix}{path}"

    def tb(self, period: str) -> str:
        """GET /api/v1/financial/tb/{period}"""
        return self.endpoint(f"/financial/tb/{period}")

    def master_tb(self) -> str:
        return self.endpoint("/financial/master-tb")

    def gl_transactions(self) -> str:
        return self.endpoint("/gl/transactions")

    def gl_balance(self, account: str) -> str:
        return self.endpoint(f"/gl/balance/{account}")

    def ar_aging(self) -> str:
        return self.endpoint("/audit/ar-aging")

    def sales_summary(self, year: int) -> str:
        return self.endpoint(f"/sales/summary/{year}")

    def cost_closing(self) -> str:
        return self.endpoint("/cost-closing/zreport")

    def health(self) -> str:
        return self.endpoint("/health")


@dataclass
class LakeConfig:
    root: Path
    bronze: BronzeConfig
    silver: SilverConfig
    gold: GoldConfig
    api: ApiConfig
    duckdb: Path
    ops_db: Path


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def _resolve(root: Path, rel: str) -> Path:
    """Resolve a relative path string against root."""
    return root / rel


def load_config(config_path: Optional[Path] = None) -> LakeConfig:
    """Load and parse data_paths.yaml into a LakeConfig object."""
    cfg_path = config_path or _find_config()
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    root = Path(raw["data_lake_root"])

    # Bronze
    br = raw["bronze"]
    bronze = BronzeConfig(
        root=_resolve(root, br["root"]),
        templates=_resolve(root, br["templates"]),
        gl=_resolve(root, br["gl"]),
        ar=_resolve(root, br["ar"]),
        ap=_resolve(root, br["ap"]),
        sales=_resolve(root, br["sales"]),
        production=_resolve(root, br["production"]),
        fixed_assets=_resolve(root, br["fixed_assets"]),
        inventory=_resolve(root, br["inventory"]),
        deposit=_resolve(root, br["deposit"]),
        files={k: _resolve(root, v) for k, v in br["files"].items()},
    )

    # Silver
    sv = raw["silver"]
    silver = SilverConfig(
        root=_resolve(root, sv["root"]),
        gl=_resolve(root, sv["gl"]),
        ar=_resolve(root, sv["ar"]),
        _sales_pattern=str(root / sv["sales"]),
        _production_pattern=str(root / sv["production"]),
    )

    # Gold
    gd = raw["gold"]
    gold = GoldConfig(
        root=_resolve(root, gd["root"]),
        gl_summary=_resolve(root, gd["gl_summary"]),
    )

    # API
    ap = raw["api"]
    api = ApiConfig(
        url=os.environ.get("DATA_LAKE_URL", ap["local_url"]),
        version=ap["version"],
        prefix=ap["prefix"],
        docs=ap["docs"],
    )

    # Database
    db = raw["database"]
    duckdb_path = _resolve(root, db["duckdb"])
    ops_db_path = _resolve(root, db["ops_db"])

    return LakeConfig(
        root=root,
        bronze=bronze,
        silver=silver,
        gold=gold,
        api=api,
        duckdb=duckdb_path,
        ops_db=ops_db_path,
    )


# ---------------------------------------------------------------------------
# Singleton — import and use directly
# ---------------------------------------------------------------------------
cfg = load_config()


# ---------------------------------------------------------------------------
# CLI: python lake_config.py → print summary
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Finance Data Lake — Configuration")
    print("=" * 50)
    print(f"Root        : {cfg.root}")
    print(f"DuckDB      : {cfg.duckdb}")
    print(f"Bronze      : {cfg.bronze.root}")
    print(f"Silver GL   : {cfg.silver.gl}")
    print(f"Gold Summary: {cfg.gold.gl_summary}")
    print(f"API URL     : {cfg.api.url}{cfg.api.prefix}")
    print()
    print("Bronze files:")
    for k, v in cfg.bronze.files.items():
        exists = "OK" if v.exists() else "MISSING"
        print(f"  [{exists}] {k}: {v.name}")
    print()
    print("Silver parquet files:")
    for label, path in [("GL", cfg.silver.gl), ("AR", cfg.silver.ar)]:
        exists = "OK" if path.exists() else "MISSING"
        print(f"  [{exists}] {label}: {path.name}")
    for year in [2023, 2024, 2025]:
        p = cfg.silver.sales(year)
        exists = "OK" if p.exists() else "MISSING"
        print(f"  [{exists}] Sales {year}: {p.name}")
