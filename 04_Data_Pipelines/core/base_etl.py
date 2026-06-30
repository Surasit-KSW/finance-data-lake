"""
core/base_etl.py — Abstract base class for all Silver ETL transforms.

Usage: subclass and implement extract(), transform(), _output_path().
The run() method orchestrates the full pipeline and returns a result dict.
"""
import sys
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from .validators import SilverValidator

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class BaseSilverETL(ABC):
    """
    Abstract base class for Bronze → Silver ETL.

    Subclasses must implement:
        extract()      → pd.DataFrame   (read from Bronze)
        transform(df)  → pd.DataFrame   (clean + normalize)
        _output_path() → Path           (Silver Parquet destination)
    """

    GL_AMOUNT_ALIASES = [
        "Amount in LC",
        "Amount in local currency",
        "Net Amount",
        "Amt.in loc.cur.",
        "Net_Amount",
        "Company Code Currency Value",
        "CCode Curr Value",
        "Amount",
    ]

    NUMERIC_KEYWORDS = ["AMOUNT", "AMT", "VALUE", "NET", "QTY", "QUANTITY", "COST", "KG", "BALANCE"]

    def __init__(
        self,
        company_code: str,
        domain: str,
        silver_path: Path,
        year: int = None,
    ):
        self.company_code = str(company_code)
        self.domain = domain
        self.silver_path = Path(silver_path)
        self.year = year
        self.validator = SilverValidator()

    # ── Abstract interface ──────────────────────────────────────

    @abstractmethod
    def extract(self) -> pd.DataFrame:
        """Read raw data from Bronze layer. Return empty DataFrame if no data."""
        ...

    @abstractmethod
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean, normalize, and enrich raw DataFrame. Must NOT add company_code."""
        ...

    @abstractmethod
    def _output_path(self) -> Path:
        """Return the Silver Parquet output path for this company + domain."""
        ...

    # ── Shared helpers (no duplication in subclasses) ──────────

    def normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Strip leading/trailing whitespace from all column names."""
        df.columns = df.columns.str.strip()
        return df

    def clean_numeric(self, df: pd.DataFrame, keywords: list = None) -> pd.DataFrame:
        """
        For columns whose names contain any keyword (case-insensitive),
        remove commas and coerce to float. Non-numeric values become NaN.
        """
        kw = [k.upper() for k in (keywords or self.NUMERIC_KEYWORDS)]
        for col in df.columns:
            if any(k in col.upper() for k in kw):
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "", regex=False).str.strip(),
                    errors="coerce",
                )
        return df

    def map_amount_column(self, df: pd.DataFrame, aliases: list = None) -> pd.DataFrame:
        """
        Find the first matching amount alias and rename it to 'Net_Amount'.
        If none found, return df unchanged (subclass should handle this case).
        """
        alias_list = aliases or self.GL_AMOUNT_ALIASES
        for alias in alias_list:
            if alias in df.columns and "Net_Amount" not in df.columns:
                df = df.rename(columns={alias: "Net_Amount"})
                return df
        return df

    def add_company_code(self, df: pd.DataFrame) -> pd.DataFrame:
        """Insert company_code as the first column."""
        df.insert(0, "company_code", self.company_code)
        return df

    # ── Pipeline runner ─────────────────────────────────────────

    def run(self) -> dict:
        """
        Full pipeline: extract → transform → add_company_code → validate → save.

        Returns:
            dict with keys: company_code, domain, rows_in, rows_out, warnings, status
        """
        print(f"\n[{self.company_code}] {self.domain} - starting")

        df_raw = self.extract()
        rows_in = len(df_raw)

        if df_raw.empty:
            print(f"  ⚠  [{self.company_code}] {self.domain} — no data found in Bronze, skipped")
            return {
                "company_code": self.company_code,
                "domain": self.domain,
                "rows_in": 0,
                "rows_out": 0,
                "warnings": ["No data found in Bronze layer"],
                "status": "skipped",
            }

        df_clean = self.transform(df_raw)
        df_final = self.add_company_code(df_clean)
        warnings = self.validator.validate(df_final, self.domain)

        self._save(df_final)
        rows_out = len(df_final)

        status = "warning" if warnings else "success"
        symbol = "✅" if status == "success" else "⚠ "
        print(f"  [{self.company_code}] {self.domain} {symbol} {rows_out:,} rows → {self._output_path().name}")
        if warnings:
            for w in warnings:
                print(f"    ⚠  {w}")

        return {
            "company_code": self.company_code,
            "domain": self.domain,
            "rows_in": rows_in,
            "rows_out": rows_out,
            "warnings": warnings,
            "status": status,
        }

    def _save(self, df: pd.DataFrame) -> None:
        """Save DataFrame to Silver Parquet. Creates parent dirs if needed."""
        out = self._output_path()
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, engine="pyarrow", index=False)
        print(f"  💾 Saved: {out}")
