"""
etl_ar.py — Bronze → Silver: Accounts Receivable ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_ar.py [--company AMC]

Output: 02_Silver_Cleaned/master_ar_{company_code}.parquet
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

# Raw SAP column → canonical Silver name
GL_ACCOUNT_ALIASES = ["GL Account", "G/L Account", "G/L Acct", "Account"]


class ARTransformETL(BaseSilverETL):
    """
    Bronze → Silver ETL for AR Data (SAP FBL5N layout).
    Reads AR_YYYY.XLSX files flat from bronze_ar_path (no year subdirs).
    Output: master_ar_{company_code}.parquet
    """

    def __init__(self, company_code: str, bronze_ar_path: Path, silver_path: Path):
        super().__init__(company_code=company_code, domain="ar", silver_path=silver_path)
        self.bronze_ar_path = Path(bronze_ar_path)
        self.connector = SAPConnector()

    def extract(self) -> pd.DataFrame:
        df = self.connector.read_flat_files(self.bronze_ar_path, glob_pattern="AR_*.XLSX")
        if df.empty:
            df = self.connector.read_flat_files(self.bronze_ar_path, glob_pattern="AR_*.xlsx")
        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.normalize_columns(df)

        # Map GL Account aliases → canonical GL_Account
        if "GL_Account" not in df.columns:
            for alias in GL_ACCOUNT_ALIASES:
                if alias in df.columns:
                    df = df.rename(columns={alias: "GL_Account"})
                    print(f"   info  Renamed '{alias}' -> GL_Account")
                    break

        # Map amount aliases → Net_Amount
        df = self.map_amount_column(df, aliases=["Net Amount", "Amount", "Balance", "Net_Amount"])

        # Clean numeric columns
        df = self.clean_numeric(df, ["AMOUNT", "AMT", "BALANCE", "VALUE", "NET"])

        # Coerce remaining object columns to string
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str)

        return df

    def _output_path(self) -> Path:
        return self.silver_path / f"master_ar_{self.company_code}.parquet"

    def _save(self, df: pd.DataFrame) -> None:
        """Delete old master_ar.parquet before saving."""
        old = self.silver_path / "master_ar.parquet"
        if old.exists():
            old.unlink()
            print(f"  Deleted old file: {old.name}")
        super()._save(df)


def main():
    parser = argparse.ArgumentParser(description="AR ETL — Bronze -> Silver")
    parser.add_argument("--company", default="AMC")
    args = parser.parse_args()

    registry = CompanyRegistry(
        config_path=PROJECT_ROOT / "08_Config" / "company_registry.yaml",
        project_root=PROJECT_ROOT,
    )
    company = registry.get(args.company)

    if "ar" not in company["bronze_paths"]:
        print(f"Company '{args.company}' has no AR Bronze path configured")
        sys.exit(1)

    etl = ARTransformETL(
        company_code=company["company_code"],
        bronze_ar_path=company["bronze_paths"]["ar"],
        silver_path=PROJECT_ROOT / "02_Silver_Cleaned",
    )
    result = etl.run()
    if result["status"] == "skipped":
        sys.exit(1)


if __name__ == "__main__":
    main()
