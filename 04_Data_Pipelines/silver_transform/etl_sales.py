"""
etl_sales.py — Bronze → Silver: Sales Data ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_sales.py [--company AMC] [--year 2026]

Output: 02_Silver_Cleaned/master_sales_{company_code}.parquet
"""
import sys
import argparse
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINES_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PIPELINES_DIR))

from core.base_etl import BaseSilverETL
from core.connectors import SAPConnector
from core.registry import CompanyRegistry

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = PIPELINES_DIR.parent


class SalesTransformETL(BaseSilverETL):
    """
    Bronze → Silver ETL for Sales Data (SAP VF05 layout).
    Supports filename patterns: sale_YYYY_MM.XLSX (old) and sale_MM.YYYY.XLSX (new 2026+).
    Output: master_sales_{company_code}.parquet
    """

    def __init__(self, company_code: str, bronze_sales_path: Path, silver_path: Path, year: int = None):
        super().__init__(company_code=company_code, domain="sales", silver_path=silver_path, year=year)
        self.bronze_sales_path = Path(bronze_sales_path)
        self.connector = SAPConnector()

    def extract(self) -> pd.DataFrame:
        def sales_filenames(yr: str, month: str):
            return [
                f"sale_{yr}_{month}.XLSX",
                f"sale_{yr}_{month}.xlsx",
                f"sale_{month}.{yr}.XLSX",
                f"sale_{month}.{yr}.xlsx",
            ]

        df = self.connector.read_monthly_files(
            bronze_path=self.bronze_sales_path,
            year=self.year,
            filename_fn=sales_filenames,
        )

        # Attach Year/Month from the filename pattern (connector doesn't know)
        if not df.empty and "Year" not in df.columns:
            df = self._inject_year_month(df)

        return df

    def _inject_year_month(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse Year/Month from Source_File column (e.g. sale_2025_01.XLSX)."""
        import re
        def parse_ym(fname):
            m = re.search(r'sale_(\d{4})_(\d{2})', str(fname), re.IGNORECASE)
            if m:
                return int(m.group(1)), int(m.group(2))
            m = re.search(r'sale_(\d{2})\.(\d{4})', str(fname), re.IGNORECASE)
            if m:
                return int(m.group(2)), int(m.group(1))
            return None, None

        years, months = zip(*df["Source_File"].map(parse_ym)) if "Source_File" in df.columns else ([], [])
        if years:
            df["Year"] = list(years)
            df["Month"] = list(months)
        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.normalize_columns(df)

        df = self.clean_numeric(df, ["AMOUNT", "QTY", "QUANTITY", "VALUE", "NET"])

        # Coerce string columns
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str)

        # Rename to canonical Silver schema name
        if "Net Value(THB)" in df.columns:
            df = df.rename(columns={"Net Value(THB)": "Net_Value_THB"})

        return df

    def _output_path(self) -> Path:
        return self.silver_path / f"master_sales_{self.company_code}.parquet"

    def _save(self, df: pd.DataFrame) -> None:
        """Delete old per-year master_sales_YYYY.parquet files before saving."""
        for old in self.silver_path.glob("master_sales_20??.parquet"):
            old.unlink()
            print(f"  Deleted old file: {old.name}")
        super()._save(df)


def main():
    parser = argparse.ArgumentParser(description="Sales ETL — Bronze -> Silver")
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

    if "sales" not in company["bronze_paths"]:
        print(f"Company '{args.company}' has no Sales Bronze path configured")
        sys.exit(1)

    etl = SalesTransformETL(
        company_code=company["company_code"],
        bronze_sales_path=company["bronze_paths"]["sales"],
        silver_path=PROJECT_ROOT / "02_Silver_Cleaned",
        year=year,
    )
    result = etl.run()
    if result["status"] == "skipped":
        sys.exit(1)


if __name__ == "__main__":
    main()
