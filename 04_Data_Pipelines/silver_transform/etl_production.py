"""
etl_production.py — Bronze → Silver: Production Data ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_production.py [--company AMC] [--year 2026]

Output: 02_Silver_Cleaned/master_production_{company_code}.parquet
"""
import sys
import re
import argparse
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINES_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PIPELINES_DIR))

from core.base_etl import BaseSilverETL
from core.registry import CompanyRegistry
from core.utils import detect_year_dirs

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = PIPELINES_DIR.parent

# Column aliases: raw SAP column name → canonical Silver schema name
COLUMN_ALIASES = {
    "Actual GR QTY":               "GR_Qty",
    "GR Qty":                      "GR_Qty",
    "GR quantity":                  "GR_Qty",
    "Actual ByProduct Scrap QTY":  "ByProduct_Scrap",
    "ByProduct Scrap":              "ByProduct_Scrap",
    "Actual ByProduct Grade B QTY": "Grade_B",
    "Grade B":                      "Grade_B",
    "Actual ByProduct Grade C QTY": "Grade_C",
    "Grade C":                      "Grade_C",
}


class ProductionTransformETL(BaseSilverETL):
    """
    Bronze → Silver ETL for Production Data (SAP MB52 layout).
    Parses Plant + Month from filenames:
      Pattern 1: PLANT_YYYY_MM.XLSX  (e.g. 1300_2025_07.XLSX)
      Pattern 2: PLANT.MM.YYYY.XLSX  (e.g. 1300.01.2026.XLSX)
    Output: master_production_{company_code}.parquet
    """

    def __init__(self, company_code: str, bronze_prod_path: Path, silver_path: Path, year: int = None):
        super().__init__(company_code=company_code, domain="production", silver_path=silver_path, year=year)
        self.bronze_prod_path = Path(bronze_prod_path)

    def _parse_filename(self, filename: str):
        """Returns (plant, year, month) or (None, None, None) if no pattern matches."""
        # Pattern 1: PLANT_YYYY_MM.XLSX
        m = re.match(r'^(\d{4})_(\d{4})_(\d{2})\.xlsx$', filename, re.IGNORECASE)
        if m:
            return m.group(1), int(m.group(2)), int(m.group(3))
        # Pattern 2: PLANT.MM.YYYY.XLSX
        m = re.match(r'^(\d{4})\.(\d{2})\.(\d{4})\.xlsx$', filename, re.IGNORECASE)
        if m:
            return m.group(1), int(m.group(3)), int(m.group(2))
        return None, None, None

    def extract(self) -> pd.DataFrame:
        if not self.bronze_prod_path.exists():
            print(f"  ⚠️  Bronze path not found: {self.bronze_prod_path}")
            return pd.DataFrame()

        years = [self.year] if self.year else detect_year_dirs(self.bronze_prod_path)
        all_frames = []

        for yr in years:
            yr_path = self.bronze_prod_path / str(yr)
            if not yr_path.exists():
                continue
            for fpath in sorted(yr_path.iterdir()):
                if not fpath.suffix.upper() == ".XLSX":
                    continue
                plant, file_year, month = self._parse_filename(fpath.name)
                if plant is None or file_year != yr:
                    continue
                print(f"  ⏳ {fpath.name} ...", end=" ")
                try:
                    df = pd.read_excel(fpath, engine="openpyxl")
                    df["Source_File"] = fpath.name
                    df["Plant"] = plant
                    df["Year"] = yr
                    df["Month"] = month
                    all_frames.append(df)
                    print(f"✅ {len(df):,} rows")
                except Exception as e:
                    print(f"❌ {e}")

        return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.normalize_columns(df)

        # Rename raw SAP column names to canonical Silver schema names
        rename_map = {raw: canonical for raw, canonical in COLUMN_ALIASES.items() if raw in df.columns}
        if rename_map:
            df = df.rename(columns=rename_map)
            for raw, canonical in rename_map.items():
                print(f"   info  Renamed '{raw}' -> {canonical}")

        # Clean numeric columns (QTY, AMOUNT, COST, KG keywords + canonical names)
        df = self.clean_numeric(df, ["AMOUNT", "QTY", "QUANTITY", "COST", "KG",
                                     "GR_Qty", "ByProduct_Scrap", "Grade_B", "Grade_C"])

        # Coerce all remaining object columns to string
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str)

        return df

    def _output_path(self) -> Path:
        return self.silver_path / f"master_production_{self.company_code}.parquet"

    def _save(self, df: pd.DataFrame) -> None:
        """Delete old per-year master_production_YYYY.parquet before saving."""
        for old in self.silver_path.glob("master_production_20??.parquet"):
            old.unlink()
            print(f"  🗑️  Deleted old file: {old.name}")
        super()._save(df)


def main():
    parser = argparse.ArgumentParser(description="Production ETL — Bronze → Silver")
    parser.add_argument("--company", default="AMC")
    parser.add_argument("--year", type=int)
    parser.add_argument("year_pos", nargs="?", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    year = args.year or args.year_pos

    registry = CompanyRegistry(
        config_path=PROJECT_ROOT / "08_Config" / "company_registry.yaml",
        project_root=PROJECT_ROOT,
    )
    company = registry.get(args.company)

    if "production" not in company["bronze_paths"]:
        print(f"❌ Company '{args.company}' has no Production Bronze path configured")
        sys.exit(1)

    etl = ProductionTransformETL(
        company_code=company["company_code"],
        bronze_prod_path=company["bronze_paths"]["production"],
        silver_path=PROJECT_ROOT / "02_Silver_Cleaned",
        year=year,
    )
    result = etl.run()
    if result["status"] == "skipped":
        sys.exit(1)


if __name__ == "__main__":
    main()
