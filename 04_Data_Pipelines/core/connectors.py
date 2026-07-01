"""
core/connectors.py — Data source connectors for ETL pipeline.

SAPConnector: reads monthly Excel exports from SAP (AMC/GA/STC).
ExcelTemplateConnector: reads manual Excel templates (AMCE/AMSB/PSM) — stub for Plan B.
"""
import sys
import pandas as pd
from pathlib import Path
from .utils import detect_year_dirs

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class SAPConnector:
    """
    Reads SAP Excel exports from Bronze layer.
    Files are organized in year subdirectories: bronze_path/YYYY/file.XLSX
    """

    def read_monthly_files(
        self,
        bronze_path: Path,
        year: int = None,
        filename_fn=None,
    ) -> pd.DataFrame:
        """
        Read monthly Excel files from year subdirectories.

        Args:
            bronze_path: Path to Bronze domain folder (e.g. 01_Bronze_Raw/gl/amc or 01_Bronze_Raw/sales/amc)
            year: If set, process only this year. If None, detect all year subdirs.
            filename_fn: Callable(year_str, month_str) -> list[str] of candidate filenames.
                         If None, reads ALL .xlsx/.XLSX files in each year dir.

        Returns:
            Concatenated DataFrame of all files found. Empty DataFrame if none.
        """
        if not bronze_path.exists():
            print(f"  ⚠️  Bronze path not found: {bronze_path}")
            return pd.DataFrame()

        years = [year] if year else detect_year_dirs(bronze_path)
        if not years:
            print(f"  ⚠️  No year subdirectories found in: {bronze_path}")
            return pd.DataFrame()

        all_frames = []
        for yr in years:
            yr_path = bronze_path / str(yr)
            if not yr_path.exists():
                print(f"  ⚠️  Year dir not found: {yr_path}")
                continue

            if filename_fn:
                months = [f"{m:02d}" for m in range(1, 13)]
                for month in months:
                    for fname in filename_fn(str(yr), month):
                        fpath = yr_path / fname
                        if fpath.exists():
                            df = self._read_excel(fpath)
                            if df is not None:
                                df["Source_File"] = fname
                                all_frames.append(df)
                            break  # found one match for this month
            else:
                # Read all .xlsx files in the year dir
                # Deduplicate by resolved path on case-insensitive filesystems (Windows)
                seen_paths = set()
                candidates = sorted(set(yr_path.glob("*.xlsx")) | set(yr_path.glob("*.XLSX")))
                for fpath in candidates:
                    resolved = fpath.resolve()
                    if resolved in seen_paths:
                        continue
                    seen_paths.add(resolved)
                    df = self._read_excel(fpath)
                    if df is not None:
                        df["Source_File"] = fpath.name
                        all_frames.append(df)

        if not all_frames:
            return pd.DataFrame()
        return pd.concat(all_frames, ignore_index=True)

    def read_flat_files(self, bronze_path: Path, glob_pattern: str = "*.XLSX") -> pd.DataFrame:
        """
        Read Excel files directly from bronze_path (no year subdirs).
        Used for AR data: 01_Bronze_Raw/ar/amc/ar_2024.xlsx
        """
        if not bronze_path.exists():
            print(f"  ⚠️  Bronze path not found: {bronze_path}")
            return pd.DataFrame()

        frames = []
        for fpath in sorted(bronze_path.glob(glob_pattern)):
            df = self._read_excel(fpath)
            if df is not None:
                df["Source_File"] = fpath.name
                frames.append(df)

        # Also try lowercase extension
        if not frames and glob_pattern.endswith(".XLSX"):
            for fpath in sorted(bronze_path.glob(glob_pattern.replace(".XLSX", ".xlsx"))):
                df = self._read_excel(fpath)
                if df is not None:
                    df["Source_File"] = fpath.name
                    frames.append(df)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _read_excel(self, fpath: Path) -> pd.DataFrame:
        """Read a single Excel file. Returns None on error."""
        print(f"  ⏳ {fpath.name} ...", end=" ")
        try:
            df = pd.read_excel(fpath, engine="openpyxl")
            print(f"✅ {len(df):,} rows")
            return df
        except Exception as e:
            print(f"❌ {e}")
            return None


class ExcelTemplateConnector:
    """
    Reads manual Excel templates from non-SAP companies (AMCE/AMSB/PSM).
    Stub — fully implemented in Plan B when templates are available.
    """

    def read_template(self, bronze_path: Path) -> pd.DataFrame:
        """Read all .xlsx files from bronze_path flat (no year subdirs)."""
        if not bronze_path.exists():
            return pd.DataFrame()
        frames = []
        # Deduplicate by resolved path on case-insensitive filesystems (Windows)
        seen_paths = set()
        candidates = sorted(set(bronze_path.glob("*.xlsx")) | set(bronze_path.glob("*.XLSX")))
        for fpath in candidates:
            resolved = fpath.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                df = pd.read_excel(fpath, engine="openpyxl")
                df["Source_File"] = fpath.name
                frames.append(df)
            except Exception as e:
                print(f"  ❌ {fpath.name}: {e}")
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
