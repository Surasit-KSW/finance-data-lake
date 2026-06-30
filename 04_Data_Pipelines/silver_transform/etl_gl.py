"""
etl_gl.py — Bronze → Silver: GL Transactions ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_gl.py [--company AMC] [--year 2026]

Output: 02_Silver_Cleaned/master_gl_{company_code}.parquet
"""
import sys
import argparse
from pathlib import Path

import pandas as pd

# ── sys.path setup สำหรับ import core ────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINES_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PIPELINES_DIR))

from core.base_etl import BaseSilverETL
from core.connectors import SAPConnector
from core.registry import CompanyRegistry

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = PIPELINES_DIR.parent


class GLTransformETL(BaseSilverETL):
    """
    Bronze → Silver ETL for GL Transactions (SAP FBL3N layout).
    Reads monthly gl_YYYY_MM.XLSX files from Bronze.
    Output: master_gl_{company_code}.parquet
    """

    GL_ACCOUNT_ALIASES = ["G/L Acct", "GL Account", "Account", "Saknr"]

    def __init__(self, company_code: str, bronze_gl_path: Path, silver_path: Path, year: int = None):
        super().__init__(company_code=company_code, domain="gl", silver_path=silver_path, year=year)
        self.bronze_gl_path = Path(bronze_gl_path)
        self.connector = SAPConnector()

    def extract(self) -> pd.DataFrame:
        def gl_filenames(yr: str, month: str):
            return [
                f"gl_{yr}_{month}.XLSX",
                f"gl_{yr}_{month}.xlsx",
            ]

        return self.connector.read_monthly_files(
            bronze_path=self.bronze_gl_path,
            year=self.year,
            filename_fn=gl_filenames,
        )

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.normalize_columns(df)

        # Map G/L Account aliases
        if "G/L Account" not in df.columns:
            for alias in self.GL_ACCOUNT_ALIASES:
                if alias in df.columns:
                    df = df.rename(columns={alias: "G/L Account"})
                    print(f"   info  Renamed '{alias}' -> G/L Account")
                    break

        # Derive Year/Month from Posting Date
        date_col = next((c for c in df.columns if "POSTING DATE" in c.upper()), None)
        if date_col and "Year" not in df.columns:
            dates = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
            df["Year"] = dates.dt.year.astype("Int64")
            df["Month"] = dates.dt.month.astype("Int64")
            print(f"   info  Derived Year/Month from '{date_col}'")

        # Map amount column
        df = self.map_amount_column(df)

        # Coerce date columns to string (prevents mixed int/str across years)
        for col in df.columns:
            if "DATE" in col.upper() and df[col].dtype == object:
                df[col] = df[col].astype(str)

        # Clean all numeric columns
        df = self.clean_numeric(df, ["AMOUNT", "AMT", "VALUE"])

        return df

    def _output_path(self) -> Path:
        return self.silver_path / f"master_gl_{self.company_code}.parquet"

    def _save(self, df: pd.DataFrame) -> None:
        """Delete old Master_GL_*.parquet before saving new file (Windows case-insensitive glob safety)."""
        for old in self.silver_path.glob("Master_GL_*.parquet"):
            old.unlink()
            print(f"  Deleted old file: {old.name}")
        # Also delete new-format files for the same company (handles re-runs on Linux CI)
        output = self._output_path()
        if output.exists():
            output.unlink()
        super()._save(df)


def main():
    parser = argparse.ArgumentParser(description="GL ETL — Bronze -> Silver")
    parser.add_argument("--company", default="AMC", help="Company name (default: AMC)")
    parser.add_argument("--year", type=int, help="Process specific year only")
    # Legacy positional arg support: python etl_gl.py 2026
    parser.add_argument("year_pos", nargs="?", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()

    year = args.year or args.year_pos

    registry = CompanyRegistry(
        config_path=PROJECT_ROOT / "08_Config" / "company_registry.yaml",
        project_root=PROJECT_ROOT,
    )
    company = registry.get(args.company)

    if "gl" not in company["bronze_paths"]:
        print(f"Company '{args.company}' has no GL Bronze path configured")
        sys.exit(1)

    etl = GLTransformETL(
        company_code=company["company_code"],
        bronze_gl_path=company["bronze_paths"]["gl"],
        silver_path=PROJECT_ROOT / "02_Silver_Cleaned",
        year=year,
    )

    result = etl.run()
    if result["status"] == "skipped":
        sys.exit(1)


if __name__ == "__main__":
    main()
