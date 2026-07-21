"""
etl_gl.py — Bronze → Silver: GL Transactions ETL
รัน: python 04_Data_Pipelines/silver_transform/etl_gl.py [--company AMC] [--year 2026]

Output: 02_Silver_Cleaned/master_gl_{company_code}.parquet
"""
import re
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


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}")


def _parse_posting_dates(series: pd.Series) -> pd.Series:
    """pd.read_excel(dtype=str) (used by upsert_file) turns native Excel date
    cells into ISO strings ("2026-04-07 00:00:00"). ISO is already unambiguous
    (year first) -- but pd.to_datetime(..., dayfirst=True) still silently swaps
    month/day whenever day<=12 and month!=day (e.g. "2026-04-07" -> 2026-07-04).
    Only apply dayfirst=True to genuine DD.MM.YYYY / DD/MM/YYYY text exports.
    Same bug/fix as cashflow/etl_fbl.py::_to_date."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    s = series.astype(str).str.strip()
    is_iso = s.str.match(_ISO_DATE_RE)
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if is_iso.any():
        parsed.loc[is_iso] = pd.to_datetime(s.loc[is_iso], dayfirst=False, errors="coerce")
    if (~is_iso).any():
        parsed.loc[~is_iso] = pd.to_datetime(s.loc[~is_iso], dayfirst=True, errors="coerce")
    return parsed


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
                f"gl_{yr}{month}.xlsx",
                f"gl_{yr}{month}.XLSX",
                f"gl_{yr}_{month}.xlsx",
                f"gl_{yr}_{month}.XLSX",
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
            dates = _parse_posting_dates(df[date_col])
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


def upsert_file(file_path: Path, company_name: str = "AMC") -> None:
    """Upsert เฉพาะไฟล์เดียว — ลบ rows เดิมของเดือนนั้น แล้ว append ใหม่"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    registry = CompanyRegistry(
        config_path=PROJECT_ROOT / "08_Config" / "company_registry.yaml",
        project_root=PROJECT_ROOT,
    )
    company = registry.get(company_name)
    etl = GLTransformETL(
        company_code=company["company_code"],
        bronze_gl_path=company["bronze_paths"]["gl"],
        silver_path=PROJECT_ROOT / "02_Silver_Cleaned",
    )

    print(f"  📄 Upsert GL: {file_path.name}")
    df_raw = pd.read_excel(file_path, dtype=str)
    df_clean = etl.transform(df_raw)
    df_final = etl.add_company_code(df_clean)
    df_final["loaded_at"] = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S +07")

    # หา month/year จากข้อมูล
    year  = int(df_final["Year"].dropna().astype(int).max())
    month = int(df_final["Month"].dropna().astype(int).max())
    print(f"     detected month={month} year={year} ({len(df_final):,} rows)")

    out = etl._output_path()
    if out.exists():
        df_existing = pd.read_parquet(out)
        # A handful of pre-existing rows can have NA Year/Month (blank posting date in
        # a prior export) -- astype(int) on those raises, so compare via the nullable
        # Int64 dtype instead (NA == year evaluates to False/pd.NA, never crashes).
        mask = (df_existing["Year"].astype("Int64") == year) & (df_existing["Month"].astype("Int64") == month)
        mask = mask.fillna(False)
        dropped = mask.sum()
        df_existing = df_existing[~mask]
        if dropped:
            print(f"  🗑  ลบ {dropped:,} rows เดิม (month={month} year={year})")
    else:
        df_existing = pd.DataFrame()

    # upsert_file reads the incoming Bronze file with dtype=str, but the original
    # full-company bulk load let pandas infer dtypes (openpyxl auto-parses numeric-
    # looking cells to float64, e.g. "Company Code" -> 1000.0). Concatenating a
    # float64 column with a str column produces a mixed-type object column that
    # pyarrow can't write -- align overlapping columns to a common dtype first.
    if not df_existing.empty:
        for col in set(df_existing.columns) & set(df_final.columns):
            if df_existing[col].dtype != df_final[col].dtype:
                try:
                    df_final[col] = df_final[col].astype(df_existing[col].dtype)
                except (ValueError, TypeError):
                    df_existing[col] = df_existing[col].astype(str)
                    df_final[col] = df_final[col].astype(str)

    combined = pd.concat([df_existing, df_final], ignore_index=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out, engine="pyarrow", index=False)
    print(f"  💾 Saved: {out.name} ({len(combined):,} rows total)")


def main():
    parser = argparse.ArgumentParser(description="GL ETL — Bronze -> Silver")
    parser.add_argument("--company", default="AMC", help="Company name (default: AMC)")
    parser.add_argument("--year", type=int, help="Process specific year only")
    parser.add_argument("--file", type=Path, default=None, help="Upsert เฉพาะไฟล์นี้ (ไม่ rebuild ทั้งหมด)")
    # Legacy positional arg support: python etl_gl.py 2026
    parser.add_argument("year_pos", nargs="?", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.file:
        upsert_file(args.file, company_name=args.company)
        return

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
